from db import get_conn, is_admin, require_admin
from datetime import date
from calendar import monthrange
import base64
import os
from pathlib import Path

# -------------------- helpers --------------------

def _to_int(x):
    x = (x or "").strip() if isinstance(x, str) else x
    return int(x) if (x is not None and x != "") else None

def _is_blank(x) -> bool:
    return x is None or (isinstance(x, str) and x.strip() == "")

def validate_date_parts(year, month, day, *, label="date"):
    def norm(name, v):
        if isinstance(v, str):
            try:
                return _to_int(v)
            except Exception:
                raise ValueError(f"{label}: {name} must be an integer or empty.")
        if v is None or isinstance(v, int):
            return v
        raise ValueError(f"{label}: {name} must be str/int/None.")

    y = norm("year", year)
    m = norm("month", month)
    d = norm("day", day)

    if y is None and m is None and d is None:
        return (None, None, None)
    if y is not None and not (1900 <= y <= 3000):
        raise ValueError(f"{label}: year must be 1900..3000.")
    if m is not None and not (1 <= m <= 12):
        raise ValueError(f"{label}: month must be 1..12.")
    if d is not None and not (1 <= d <= 31):
        raise ValueError(f"{label}: day must be 1..31.")

    if d is not None and m is not None:
        if y is not None:
            _, dim = monthrange(y, m)
        else:
            dim = 29 if m == 2 else (30 if m in (4, 6, 9, 11) else 31)
        if d > dim:
            if y is not None:
                raise ValueError(f"{label}: {y}-{m:02d} has {dim} days; got {d}.")
            else:
                raise ValueError(f"{label}: month {m} allows up to {dim} days; got {d}.")
    if y is not None and m is not None and d is not None:
        date(y, m, d)
    return (y, m, d)

# -------------------- file storage helpers --------------------

def _files_dir() -> Path:
    """
    Returns the repository-local directory where we store uploaded files.
    Creates it on first use: <this_file_dir>/files
    """
    base = Path(__file__).resolve().parent
    d = base / "files"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _derive_target_name(oid: int, src_path: str) -> str:
    """
    Make a deterministic filename based on the allocated oid and original extension.
    Example: 42.pdf  /  7__scan.png
    """
    p = Path(src_path)
    ext = p.suffix if p.suffix else ""
    safe_ext = ext if len(ext) <= 10 and all(c.isalnum() or c in ('.',) for c in ext) else ""
    # prefix with oid to guarantee uniqueness
    return f"{oid}{safe_ext}"

def lo_save_file(path: str) -> int:
    """
    Store file bytes on disk under ./files/ and create a :Blob node with {oid, url}.
    Returns the allocated oid.
    """
    # Read source file
    with open(path, "rb") as f:
        data = f.read()

    with get_conn() as s:
        # allocate new oid
        rec = s.run("""
            MERGE (c:Counters {id:'global'})
            ON CREATE SET c.lo_oid = 0
            SET c.lo_oid = c.lo_oid + 1
            RETURN c.lo_oid AS oid
        """).single()
        oid = rec["oid"]

        # write to repo-local ./files directory
        files_dir = _files_dir()
        target_name = _derive_target_name(oid, path)
        target_path = files_dir / target_name
        with open(target_path, "wb") as out:
            out.write(data)

        # store only URL (relative path) in DB
        
        url = f"files/{target_name}"
        s.run("""
            CREATE (b:Blob {oid:$oid, url:$url})
        """, oid=oid, url=url)

        return oid

# -------------------- CLINIC --------------------

def clinic_view():
    with get_conn() as s:
        rs = s.run("""
            MATCH (c:Clinic)
            RETURN c.cli_id AS cli_id, c.cli_name AS cli_name, c.address AS address
            ORDER BY cli_id
        """)
        return [(r["cli_id"], r["cli_name"], r["address"]) for r in rs]

def clinic_search(cli_id="", cli_name="", address=""):
    where = []
    params = {}
    if cli_id:
        where.append("c.cli_id CONTAINS $cli_id"); params["cli_id"] = cli_id
    if cli_name:
        where.append("c.cli_name CONTAINS $cli_name"); params["cli_name"] = cli_name
    if address:
        where.append("c.address CONTAINS $address"); params["address"] = address
    clause = " WHERE " + " AND ".join(where) if where else ""
    with get_conn() as s:
        rs = s.run(f"""
            MATCH (c:Clinic){clause}
            RETURN c.cli_id AS cli_id, c.cli_name AS cli_name, c.address AS address
            ORDER BY cli_id
        """, **params)
        return [(r["cli_id"], r["cli_name"], r["address"]) for r in rs]

def clinic_insert(cli_id: str, cli_name: str, address: str | None):
    require_admin()
    with get_conn() as s:
        s.run("""
            MERGE (c:Clinic {cli_id:$id})
            SET c.cli_name=$nm, c.address=$addr
        """, id=cli_id, nm=cli_name, addr=(address or None))

def clinic_update(cli_id: str, cli_name: str | None = None, address: str | None = None):
    require_admin()
    sets = []
    params = {"id": cli_id}
    if not _is_blank(cli_name): sets.append("c.cli_name=$nm"); params["nm"] = cli_name
    if not _is_blank(address):  sets.append("c.address=$addr"); params["addr"] = address
    if not sets:
        return
    with get_conn() as s:
        s.run(f"""
            MATCH (c:Clinic {{cli_id:$id}})
            SET {", ".join(sets)}
        """, **params)

def clinic_delete(cli_id: str):
    require_admin()
    with get_conn() as s:
        s.run("""
            MATCH (c:Clinic {cli_id:$id})
            DETACH DELETE c
        """, id=cli_id)

# -------------------- DEPARTMENT --------------------

def department_view():
    with get_conn() as s:
        rs = s.run("""
            MATCH (d:Department)
            OPTIONAL MATCH (d)-[:BELONGS_TO]->(c:Clinic)
            RETURN d.dept_id AS dept_id, d.dept_name AS dept_name, c.cli_id AS cli_id, c.cli_name AS cli_name
            ORDER BY dept_id
        """)
        return [(r["dept_id"], r["dept_name"], r["cli_id"], r["cli_name"]) for r in rs]

def department_search(dept_id="", dept_name="", cli_id="", clinic_name=""):
    where = []
    params = {}
    if dept_id:
        where.append("d.dept_id CONTAINS $dept_id"); params["dept_id"] = dept_id
    if dept_name:
        where.append("d.dept_name CONTAINS $dept_name"); params["dept_name"] = dept_name
    if cli_id:
        where.append("c.cli_id CONTAINS $cli_id"); params["cli_id"] = cli_id
    if clinic_name:
        where.append("c.cli_name CONTAINS $clinic_name"); params["clinic_name"] = clinic_name
    clause = "WHERE " + " AND ".join(where) if where else ""
    with get_conn() as s:
        rs = s.run(f"""
            MATCH (d:Department)
            OPTIONAL MATCH (d)-[:BELONGS_TO]->(c:Clinic)
            WITH d, c
            {clause}
            RETURN d.dept_id AS dept_id, d.dept_name AS dept_name, c.cli_id AS cli_id, c.cli_name AS cli_name
            ORDER BY dept_id
        """, **params)
        return [(r["dept_id"], r["dept_name"], r["cli_id"], r["cli_name"]) for r in rs]


def department_insert(dept_id: str, dept_name: str, cli_id: str | None):
    require_admin()
    with get_conn() as s:
        if _is_blank(cli_id):
            s.run("MERGE (:Department {dept_id:$id}) SET _.dept_name=$nm", id=dept_id, nm=dept_name)
        else:
            s.run("""
                MERGE (d:Department {dept_id:$id})
                SET d.dept_name=$nm
                WITH d
                MATCH (c:Clinic {cli_id:$cli})
                MERGE (d)-[:BELONGS_TO]->(c)
            """, id=dept_id, nm=dept_name, cli=cli_id)

def department_update(dept_id: str, dept_name: str | None = None, cli_id: str | None = None):
    require_admin()
    with get_conn() as s:
        if not _is_blank(dept_name):
            s.run("MATCH (d:Department {dept_id:$id}) SET d.dept_name=$nm", id=dept_id, nm=dept_name)
        if not _is_blank(cli_id):
            s.run("""
                MATCH (d:Department {dept_id:$id})
                OPTIONAL MATCH (d)-[r:BELONGS_TO]->(:Clinic)
                DELETE r
                WITH d
                MATCH (c:Clinic {cli_id:$cli})
                MERGE (d)-[:BELONGS_TO]->(c)
            """, id=dept_id, cli=cli_id)

def department_delete(dept_id: str):
    require_admin()
    with get_conn() as s:
        s.run("MATCH (d:Department {dept_id:$id}) DETACH DELETE d", id=dept_id)

# -------------------- DOCTOR --------------------

def doctor_view():
    with get_conn() as s:
        rs = s.run("""
            MATCH (d:Doctor)
            OPTIONAL MATCH (d)-[:WORKS_IN]->(dept:Department)
            OPTIONAL MATCH (p:Patient)-[:ASSIGNED_TO]->(d)
            WITH d, dept, collect(DISTINCT {patient_ID:p.patient_ID, patient_name:p.name}) AS patients
            WITH d, dept, patients
            RETURN DISTINCT
                d.doctor_ID AS doctor_personnumer,
                d.name      AS doctor_name,
                dept.dept_id AS dept_id,
                // For backward compatibility we return one patient row at a time like the old join
                patients
            ORDER BY doctor_personnumer
        """)
       
        out = []
        for r in rs:
            d_id   = r["doctor_personnumer"]
            d_name = r["doctor_name"]
            dept   = r["dept_id"]
            pats   = r["patients"] or []
            if not pats:
                out.append((d_id, d_name, dept, None, None))
            else:
                for p in pats:
                    out.append((d_id, d_name, dept, p.get("patient_ID"), p.get("patient_name")))
        return out

def doctor_search(doctor_name="", doctor_personnumer="", patient_name="", patient_personnumer=""):
    where = []
    params = {}
    if doctor_name:
        where.append("d.name CONTAINS $dname"); params["dname"] = doctor_name
    if doctor_personnumer:
        where.append("d.doctor_ID CONTAINS $did"); params["did"] = doctor_personnumer
    if patient_name:
        where.append("p.name CONTAINS $pname"); params["pname"] = patient_name
    if patient_personnumer:
        where.append("p.patient_ID CONTAINS $pid"); params["pid"] = patient_personnumer
    clause = "WHERE " + " AND ".join(where) if where else ""
    with get_conn() as s:
        rs = s.run(f"""
            MATCH (d:Doctor)
            OPTIONAL MATCH (p:Patient)-[:ASSIGNED_TO]->(d)
            OPTIONAL MATCH (d)-[:WORKS_IN]->(dept:Department)
            WITH d, p, dept
            {clause}
            RETURN DISTINCT
                d.doctor_ID AS doctor_personnumer,
                d.name      AS doctor_name,
                dept.dept_id AS dept_id,
                p.patient_ID AS patient_personnumer,
                p.name       AS patient_name
            ORDER BY doctor_personnumer
        """, **params)
        return [(r["doctor_personnumer"], r["doctor_name"], r["dept_id"],
                 r["patient_personnumer"], r["patient_name"]) for r in rs]


def doctor_insert(doctor_personnumer: str, doctor_name: str, dept_id: str | None):
    require_admin()
    with get_conn() as s:
        s.run("""
            MERGE (d:Doctor {doctor_ID:$id})
            SET d.name=$nm
        """, id=doctor_personnumer, nm=doctor_name)
        if not _is_blank(dept_id):
            s.run("""
                MATCH (d:Doctor {doctor_ID:$id})
                MATCH (dept:Department {dept_id:$dept})
                MERGE (d)-[:WORKS_IN]->(dept)
            """, id=doctor_personnumer, dept=dept_id)

def doctor_update(doctor_personnumer: str,
                  new_dept_id: str | None = None,
                  new_doctor_name: str | None = None):
    require_admin()
    with get_conn() as s:
        if not _is_blank(new_doctor_name):
            s.run("MATCH (d:Doctor {doctor_ID:$id}) SET d.name=$nm",
                  id=doctor_personnumer, nm=new_doctor_name)
        if not _is_blank(new_dept_id):
            s.run("""
                MATCH (d:Doctor {doctor_ID:$id})
                OPTIONAL MATCH (d)-[r:WORKS_IN]->(:Department)
                DELETE r
                WITH d
                MATCH (dept:Department {dept_id:$dept})
                MERGE (d)-[:WORKS_IN]->(dept)
            """, id=doctor_personnumer, dept=new_dept_id)

def doctor_delete(doctor_personnumer: str):
    require_admin()
    with get_conn() as s:
        s.run("MATCH (d:Doctor {doctor_ID:$id}) DETACH DELETE d", id=doctor_personnumer)

# -------------------- PATIENT --------------------

def patient_view():
    with get_conn() as s:
        rs = s.run("""
            MATCH (pa:Patient)
            OPTIONAL MATCH (pa)-[:ASSIGNED_TO]->(d:Doctor)
            RETURN
                pa.patient_ID AS patient_personnumer,
                pa.name       AS patient_name,
                d.doctor_ID   AS doctor_personnumer,
                d.name        AS doctor_name
            ORDER BY patient_personnumer
        """)
        return [(r["patient_personnumer"], r["patient_name"],
                 r["doctor_personnumer"], r["doctor_name"]) for r in rs]

def patient_search(patient_name="", patient_personnumer="", doctor_name="", doctor_personnumer=""):
    where = []
    params = {}
    if patient_name:
        where.append("pa.name CONTAINS $pname"); params["pname"] = patient_name
    if patient_personnumer:
        where.append("pa.patient_ID CONTAINS $pid"); params["pid"] = patient_personnumer
    if doctor_name:
        where.append("d.name CONTAINS $dname"); params["dname"] = doctor_name
    if doctor_personnumer:
        where.append("d.doctor_ID CONTAINS $did"); params["did"] = doctor_personnumer
    clause = "WHERE " + " AND ".join(where) if where else ""
    with get_conn() as s:
        rs = s.run(f"""
            MATCH (pa:Patient)
            OPTIONAL MATCH (pa)-[:ASSIGNED_TO]->(d:Doctor)
            WITH pa, d
            {clause}
            RETURN
                pa.patient_ID AS patient_personnumer,
                pa.name       AS patient_name,
                d.doctor_ID   AS doctor_personnumer,
                d.name        AS doctor_name
            ORDER BY patient_personnumer
        """, **params)
        return [(r["patient_personnumer"], r["patient_name"],
                 r["doctor_personnumer"], r["doctor_name"]) for r in rs]


def patient_insert(patient_personnumer: str, patient_name: str, doctor_personnumer: str | None):
    require_admin()
    with get_conn() as s:
        s.run("""
            MERGE (p:Patient {patient_ID:$pid})
            SET p.name=$nm
        """, pid=patient_personnumer, nm=patient_name)
        if not _is_blank(doctor_personnumer):
            s.run("""
                MATCH (p:Patient {patient_ID:$pid})
                MATCH (d:Doctor  {doctor_ID:$did})
                MERGE (p)-[:ASSIGNED_TO]->(d)
            """, pid=patient_personnumer, did=doctor_personnumer)

def patient_update(patient_personnumer: str,
                   new_doctor_personnumer: str | None = None,
                   new_patient_name: str | None = None):
    require_admin()
    with get_conn() as s:
        if not _is_blank(new_patient_name):
            s.run("""
                MATCH (p:Patient {patient_ID:$pid})
                SET p.name=$nm
            """, pid=patient_personnumer, nm=new_patient_name)
        if not _is_blank(new_doctor_personnumer):
            s.run("""
                MATCH (p:Patient {patient_ID:$pid})
                OPTIONAL MATCH (p)-[r:ASSIGNED_TO]->(:Doctor)
                DELETE r
                WITH p
                MATCH (d:Doctor {doctor_ID:$did})
                MERGE (p)-[:ASSIGNED_TO]->(d)
            """, pid=patient_personnumer, did=new_doctor_personnumer)

def patient_delete(patient_personnumer: str):
    require_admin()
    with get_conn() as s:
        s.run("MATCH (p:Patient {patient_ID:$pid}) DETACH DELETE p", pid=patient_personnumer)

# -------------------- APPOINTMENT --------------------

def appointment_view():
    with get_conn() as s:
        rs = s.run("""
            MATCH (a:Appointment)
            OPTIONAL MATCH (a)-[:PATIENT]->(p:Patient)
            OPTIONAL MATCH (a)-[:DOCTOR]->(d:Doctor)
            RETURN a.appoint_id AS appoint_id,
                   a.appoint_year AS appoint_year,
                   a.appoint_month AS appoint_month,
                   a.appoint_day AS appoint_day,
                   a.appoint_location AS appoint_location,
                   p.patient_ID AS patient_personnumer,
                   p.name AS patient_name,
                   d.doctor_ID AS doctor_personnumer,
                   d.name AS doctor_name
            ORDER BY a.appoint_year, a.appoint_month, a.appoint_day, a.appoint_id
        """)
        return [(r["appoint_id"], r["appoint_year"], r["appoint_month"], r["appoint_day"],
                 r["appoint_location"], r["patient_personnumer"], r["patient_name"],
                 r["doctor_personnumer"], r["doctor_name"]) for r in rs]

def appointment_search(appoint_id="", year="", month="", day="",
                       patient_name="", patient_personnumer="",
                       doctor_name="", doctor_personnumer=""):
    where = []
    params = {}
    if appoint_id:
        where.append("a.appoint_id CONTAINS $aid"); params["aid"] = appoint_id
    if year:
        where.append("a.appoint_year = $yy"); params["yy"] = _to_int(year)
    if month:
        where.append("a.appoint_month = $mm"); params["mm"] = _to_int(month)
    if day:
        where.append("a.appoint_day = $dd"); params["dd"] = _to_int(day)
    if patient_name:
        where.append("p.name CONTAINS $pname"); params["pname"] = patient_name
    if patient_personnumer:
        where.append("p.patient_ID CONTAINS $pid"); params["pid"] = patient_personnumer
    if doctor_name:
        where.append("d.name CONTAINS $dname"); params["dname"] = doctor_name
    if doctor_personnumer:
        where.append("d.doctor_ID CONTAINS $did"); params["did"] = doctor_personnumer
    clause = "WHERE " + " AND ".join(where) if where else ""
    with get_conn() as s:
        rs = s.run(f"""
            MATCH (a:Appointment)
            OPTIONAL MATCH (a)-[:PATIENT]->(p:Patient)
            OPTIONAL MATCH (a)-[:DOCTOR]->(d:Doctor)
            WITH a, p, d
            {clause}
            RETURN a.appoint_id AS appoint_id,
                   a.appoint_year AS appoint_year,
                   a.appoint_month AS appoint_month,
                   a.appoint_day AS appoint_day,
                   a.appoint_location AS appoint_location,
                   p.patient_ID AS patient_personnumer,
                   p.name AS patient_name,
                   d.doctor_ID AS doctor_personnumer,
                   d.name AS doctor_name
            ORDER BY a.appoint_year, a.appoint_month, a.appoint_day, a.appoint_id
        """, **params)
        return [(r["appoint_id"], r["appoint_year"], r["appoint_month"], r["appoint_day"],
                 r["appoint_location"], r["patient_personnumer"], r["patient_name"],
                 r["doctor_personnumer"], r["doctor_name"]) for r in rs]


def appointment_insert(appoint_id: str, year: str, month: str, day: str,
                       location: str, patient_personnumer: str | None, doctor_personnumer: str | None):
    require_admin()
    y, m, d = validate_date_parts(year, month, day, label="appointment date")
    with get_conn() as s:
        s.run("""
            MERGE (a:Appointment {appoint_id:$id})
            SET a.appoint_year=$yy, a.appoint_month=$mm, a.appoint_day=$dd, a.appoint_location=$loc
        """, id=appoint_id, yy=y, mm=m, dd=d, loc=(location or None))
        if not _is_blank(patient_personnumer):
            s.run("""
                MATCH (a:Appointment {appoint_id:$id})
                OPTIONAL MATCH (a)-[r:PATIENT]->(:Patient)
                DELETE r
                WITH a
                MATCH (p:Patient {patient_ID:$pid})
                MERGE (a)-[:PATIENT]->(p)
            """, id=appoint_id, pid=patient_personnumer)
        if not _is_blank(doctor_personnumer):
            s.run("""
                MATCH (a:Appointment {appoint_id:$id})
                OPTIONAL MATCH (a)-[r:DOCTOR]->(:Doctor)
                DELETE r
                WITH a
                MATCH (d:Doctor {doctor_ID:$did})
                MERGE (a)-[:DOCTOR]->(d)
            """, id=appoint_id, did=doctor_personnumer)

def appointment_update(appoint_id: str, year: str | None = None, month: str | None = None, day: str | None = None,
                       location: str | None = None, patient_personnumer: str | None = None, doctor_personnumer: str | None = None):
    require_admin()
    y_in = None if _is_blank(year)  else _to_int(year) if isinstance(year, str)  else year
    m_in = None if _is_blank(month) else _to_int(month) if isinstance(month, str) else month
    d_in = None if _is_blank(day)   else _to_int(day) if isinstance(day, str)   else day

    with get_conn() as s:
        # Merge existing date with new parts (read old)
        old = s.run("MATCH (a:Appointment {appoint_id:$id}) "
                    "RETURN a.appoint_year AS y, a.appoint_month AS m, a.appoint_day AS d",
                    id=appoint_id).single()
        if not old:
            raise ValueError("appointment not found")
        merged_y = y_in if y_in is not None else old["y"]
        merged_m = m_in if m_in is not None else old["m"]
        merged_d = d_in if d_in is not None else old["d"]
        validate_date_parts(merged_y, merged_m, merged_d, label="appointment date")

        sets = []
        params = {"id": appoint_id}
        if y_in is not None: sets.append("a.appoint_year=$yy"); params["yy"] = y_in
        if m_in is not None: sets.append("a.appoint_month=$mm"); params["mm"] = m_in
        if d_in is not None: sets.append("a.appoint_day=$dd");  params["dd"] = d_in
        if not _is_blank(location): sets.append("a.appoint_location=$loc"); params["loc"] = location
        if sets:
            s.run(f"MATCH (a:Appointment {{appoint_id:$id}}) SET {', '.join(sets)}", **params)

        if not _is_blank(patient_personnumer):
            s.run("""
                MATCH (a:Appointment {appoint_id:$id})
                OPTIONAL MATCH (a)-[r:PATIENT]->(:Patient)
                DELETE r
                WITH a
                MATCH (p:Patient {patient_ID:$pid})
                MERGE (a)-[:PATIENT]->(p)
            """, id=appoint_id, pid=patient_personnumer)

        if not _is_blank(doctor_personnumer):
            s.run("""
                MATCH (a:Appointment {appoint_id:$id})
                OPTIONAL MATCH (a)-[r:DOCTOR]->(:Doctor)
                DELETE r
                WITH a
                MATCH (d:Doctor {doctor_ID:$did})
                MERGE (a)-[:DOCTOR]->(d)
            """, id=appoint_id, did=doctor_personnumer)

def appointment_delete(appoint_id: str):
    require_admin()
    with get_conn() as s:
        s.run("MATCH (a:Appointment {appoint_id:$id}) DETACH DELETE a", id=appoint_id)

# -------------------- OBSERVATION --------------------

def observation_view():
    with get_conn() as s:
        rs = s.run("""
            MATCH (o:Observation)
            OPTIONAL MATCH (o)-[:OF_APPOINTMENT]->(a:Appointment)
            OPTIONAL MATCH (a)-[:PATIENT]->(p:Patient)
            OPTIONAL MATCH (a)-[:DOCTOR]->(d:Doctor)
            OPTIONAL MATCH (o)-[:FILE]->(b:Blob)
            RETURN o.obser_id   AS obser_id,
                   o.obs_year   AS obs_year,
                   o.obs_month  AS obs_month,
                   o.obs_day    AS obs_day,
                   a.appoint_id AS appoint_id,
                   p.patient_ID AS patient_personnumer,
                   p.name       AS patient_name,
                   d.doctor_ID  AS doctor_personnumer,
                   d.name       AS doctor_name,
                   o.obs_comment_text AS obs_comment_text,
                   b.oid        AS obs_file_oid
            ORDER BY obser_id
        """)
        return [(r["obser_id"], r["obs_year"], r["obs_month"], r["obs_day"],
                 r["appoint_id"], r["patient_personnumer"], r["patient_name"],
                 r["doctor_personnumer"], r["doctor_name"],
                 r["obs_comment_text"], r["obs_file_oid"]) for r in rs]

def observation_search(obser_id="", year="", month="", day="", appoint_id="",
                       patient_name="", patient_personnumer="",
                       doctor_name="", doctor_personnumer=""):
    where = []
    params = {}
    if obser_id:
        where.append("o.obser_id CONTAINS $oid"); params["oid"] = obser_id
    if year:
        where.append("o.obs_year = $yy"); params["yy"] = _to_int(year)
    if month:
        where.append("o.obs_month = $mm"); params["mm"] = _to_int(month)
    if day:
        where.append("o.obs_day = $dd"); params["dd"] = _to_int(day)
    if appoint_id:
        where.append("a.appoint_id CONTAINS $aid"); params["aid"] = appoint_id
    if patient_name:
        where.append("p.name CONTAINS $pname"); params["pname"] = patient_name
    if patient_personnumer:
        where.append("p.patient_ID CONTAINS $pid"); params["pid"] = patient_personnumer
    if doctor_name:
        where.append("d.name CONTAINS $dname"); params["dname"] = doctor_name
    if doctor_personnumer:
        where.append("d.doctor_ID CONTAINS $did"); params["did"] = doctor_personnumer
    clause = "WHERE " + " AND ".join(where) if where else ""
    with get_conn() as s:
        rs = s.run(f"""
            MATCH (o:Observation)
            OPTIONAL MATCH (o)-[:OF_APPOINTMENT]->(a:Appointment)
            OPTIONAL MATCH (a)-[:PATIENT]->(p:Patient)
            OPTIONAL MATCH (a)-[:DOCTOR]->(d:Doctor)
            OPTIONAL MATCH (o)-[:FILE]->(b:Blob)
            WITH o, a, p, d, b
            {clause}
            RETURN o.obser_id   AS obser_id,
                   o.obs_year   AS obs_year,
                   o.obs_month  AS obs_month,
                   o.obs_day    AS obs_day,
                   a.appoint_id AS appoint_id,
                   p.patient_ID AS patient_personnumer,
                   p.name       AS patient_name,
                   d.doctor_ID  AS doctor_personnumer,
                   d.name       AS doctor_name,
                   o.obs_comment_text AS obs_comment_text,
                   b.oid        AS obs_file_oid
            ORDER BY obser_id
        """, **params)
        return [(r["obser_id"], r["obs_year"], r["obs_month"], r["obs_day"],
                 r["appoint_id"], r["patient_personnumer"], r["patient_name"],
                 r["doctor_personnumer"], r["doctor_name"],
                 r["obs_comment_text"], r["obs_file_oid"]) for r in rs]

def observation_insert(obser_id: str, year: str, month: str, day: str,
                       appoint_id: str | None,
                       comment_text: str | None,
                       file_oid: int | None):
    require_admin()
    y, m, d = validate_date_parts(year, month, day, label="observation date")
    with get_conn() as s:
        s.run("""
            MERGE (o:Observation {obser_id:$id})
            SET o.obs_year=$yy, o.obs_month=$mm, o.obs_day=$dd, o.obs_comment_text=$txt
        """, id=obser_id, yy=y, mm=m, dd=d, txt=(comment_text or None))
        if not _is_blank(appoint_id):
            s.run("""
                MATCH (o:Observation {obser_id:$id})
                OPTIONAL MATCH (o)-[r:OF_APPOINTMENT]->(:Appointment)
                DELETE r
                WITH o
                MATCH (a:Appointment {appoint_id:$aid})
                MERGE (o)-[:OF_APPOINTMENT]->(a)
            """, id=obser_id, aid=appoint_id)
        if file_oid is not None:
            s.run("""
                MATCH (o:Observation {obser_id:$id})
                OPTIONAL MATCH (o)-[r:FILE]->(:Blob)
                DELETE r
                WITH o
                MATCH (b:Blob {oid:$oid})
                MERGE (o)-[:FILE]->(b)
            """, id=obser_id, oid=file_oid)

def observation_update(obser_id: str, year: str | None = None, month: str | None = None, day: str | None = None,
                       appoint_id: str | None = None,
                       comment_text: str | None = None,
                       file_oid: int | None = None):
    require_admin()
    y_in = None if _is_blank(year)  else _to_int(year) if isinstance(year, str)  else year
    m_in = None if _is_blank(month) else _to_int(month) if isinstance(month, str) else month
    d_in = None if _is_blank(day)   else _to_int(day) if isinstance(day, str)   else day
    with get_conn() as s:
        old = s.run("MATCH (o:Observation {obser_id:$id}) "
                    "RETURN o.obs_year AS y, o.obs_month AS m, o.obs_day AS d",
                    id=obser_id).single()
        if not old:
            raise ValueError("observation not found")
        merged_y = y_in if y_in is not None else old["y"]
        merged_m = m_in if m_in is not None else old["m"]
        merged_d = d_in if d_in is not None else old["d"]
        validate_date_parts(merged_y, merged_m, merged_d, label="observation date")

        sets = []
        params = {"id": obser_id}
        if y_in is not None: sets.append("o.obs_year=$yy"); params["yy"] = y_in
        if m_in is not None: sets.append("o.obs_month=$mm"); params["mm"] = m_in
        if d_in is not None: sets.append("o.obs_day=$dd");  params["dd"] = d_in
        if comment_text is not None: sets.append("o.obs_comment_text=$txt"); params["txt"] = comment_text
        if sets:
            s.run(f"MATCH (o:Observation {{obser_id:$id}}) SET {', '.join(sets)}", **params)

        if not _is_blank(appoint_id):
            s.run("""
                MATCH (o:Observation {obser_id:$id})
                OPTIONAL MATCH (o)-[r:OF_APPOINTMENT]->(:Appointment)
                DELETE r
                WITH o
                MATCH (a:Appointment {appoint_id:$aid})
                MERGE (o)-[:OF_APPOINTMENT]->(a)
            """, id=obser_id, aid=appoint_id)

        if file_oid is not None:
            s.run("""
                MATCH (o:Observation {obser_id:$id})
                OPTIONAL MATCH (o)-[r:FILE]->(:Blob)
                DELETE r
                WITH o
                MATCH (b:Blob {oid:$oid})
                MERGE (o)-[:FILE]->(b)
            """, id=obser_id, oid=file_oid)

def observation_delete(obser_id: str):
    require_admin()
    with get_conn() as s:
        s.run("MATCH (o:Observation {obser_id:$id}) DETACH DELETE o", id=obser_id)

# -------------------- DIAGNOSIS --------------------

def diagnosis_view():
    with get_conn() as s:
        rs = s.run("""
            MATCH (dg:Diagnosis)
            OPTIONAL MATCH (dg)-[:OF_OBSERVATION]->(o:Observation)
            OPTIONAL MATCH (o)-[:OF_APPOINTMENT]->(a:Appointment)
            OPTIONAL MATCH (a)-[:PATIENT]->(p:Patient)
            OPTIONAL MATCH (a)-[:DOCTOR]->(d:Doctor)
            OPTIONAL MATCH (dg)-[:FILE]->(b:Blob)
            RETURN dg.diagn_id AS diagn_id, dg.diagn_year AS diagn_year, dg.diagn_month AS diagn_month, dg.diagn_day AS diagn_day,
                   o.obser_id AS obser_id, a.appoint_id AS appoint_id,
                   p.patient_ID AS patient_personnumer, p.name AS patient_name,
                   d.doctor_ID AS doctor_personnumer, d.name AS doctor_name,
                   dg.diagn_comment_text AS diagn_comment_text, b.oid AS diagn_file_oid
            ORDER BY diagn_id
        """)
        return [(r["diagn_id"], r["diagn_year"], r["diagn_month"], r["diagn_day"],
                 r["obser_id"], r["appoint_id"], r["patient_personnumer"], r["patient_name"],
                 r["doctor_personnumer"], r["doctor_name"], r["diagn_comment_text"], r["diagn_file_oid"]) for r in rs]

def diagnosis_search(diagn_id="", year="", month="", day="", obser_id="", appoint_id="",
                     patient_name="", patient_personnumer="",
                     doctor_name="", doctor_personnumer=""):
    where = []
    params = {}
    if diagn_id:
        where.append("dg.diagn_id CONTAINS $gid"); params["gid"] = diagn_id
    if year:
        where.append("dg.diagn_year = $yy"); params["yy"] = _to_int(year)
    if month:
        where.append("dg.diagn_month = $mm"); params["mm"] = _to_int(month)
    if day:
        where.append("dg.diagn_day = $dd"); params["dd"] = _to_int(day)
    if obser_id:
        where.append("o.obser_id CONTAINS $oid"); params["oid"] = obser_id
    if appoint_id:
        where.append("a.appoint_id CONTAINS $aid"); params["aid"] = appoint_id
    if patient_name:
        where.append("p.name CONTAINS $pname"); params["pname"] = patient_name
    if patient_personnumer:
        where.append("p.patient_ID CONTAINS $pid"); params["pid"] = patient_personnumer
    if doctor_name:
        where.append("d.name CONTAINS $dname"); params["dname"] = doctor_name
    if doctor_personnumer:
        where.append("d.doctor_ID CONTAINS $did"); params["did"] = doctor_personnumer
    clause = "WHERE " + " AND ".join(where) if where else ""
    with get_conn() as s:
        rs = s.run(f"""
            MATCH (dg:Diagnosis)
            OPTIONAL MATCH (dg)-[:OF_OBSERVATION]->(o:Observation)
            OPTIONAL MATCH (o)-[:OF_APPOINTMENT]->(a:Appointment)
            OPTIONAL MATCH (a)-[:PATIENT]->(p:Patient)
            OPTIONAL MATCH (a)-[:DOCTOR]->(d:Doctor)
            OPTIONAL MATCH (dg)-[:FILE]->(b:Blob)
            WITH dg, o, a, p, d, b
            {clause}
            RETURN dg.diagn_id AS diagn_id, dg.diagn_year AS diagn_year, dg.diagn_month AS diagn_month, dg.diagn_day AS diagn_day,
                   o.obser_id AS obser_id, a.appoint_id AS appoint_id,
                   p.patient_ID AS patient_personnumer, p.name AS patient_name,
                   d.doctor_ID AS doctor_personnumer, d.name AS doctor_name,
                   dg.diagn_comment_text AS diagn_comment_text, b.oid AS diagn_file_oid
            ORDER BY diagn_id
        """, **params)
        return [(r["diagn_id"], r["diagn_year"], r["diagn_month"], r["diagn_day"],
                 r["obser_id"], r["appoint_id"], r["patient_personnumer"], r["patient_name"],
                 r["doctor_personnumer"], r["doctor_name"], r["diagn_comment_text"], r["diagn_file_oid"]) for r in rs]

def diagnosis_insert(diagn_id: str, year: str, month: str, day: str,
                     obser_id: str | None,
                     comment_text: str | None,
                     file_oid: int | None):
    require_admin()
    y, m, d = validate_date_parts(year, month, day, label="diagnosis date")
    with get_conn() as s:
        s.run("""
            MERGE (g:Diagnosis {diagn_id:$id})
            SET g.diagn_year=$yy, g.diagn_month=$mm, g.diagn_day=$dd, g.diagn_comment_text=$txt
        """, id=diagn_id, yy=y, mm=m, dd=d, txt=(comment_text or None))
        if not _is_blank(obser_id):
            s.run("""
                MATCH (g:Diagnosis {diagn_id:$id})
                OPTIONAL MATCH (g)-[r:OF_OBSERVATION]->(:Observation)
                DELETE r
                WITH g
                MATCH (o:Observation {obser_id:$oid})
                MERGE (g)-[:OF_OBSERVATION]->(o)
            """, id=diagn_id, oid=obser_id)
        if file_oid is not None:
            s.run("""
                MATCH (g:Diagnosis {diagn_id:$id})
                OPTIONAL MATCH (g)-[r:FILE]->(:Blob)
                DELETE r
                WITH g
                MATCH (b:Blob {oid:$oid})
                MERGE (g)-[:FILE]->(b)
            """, id=diagn_id, oid=file_oid)

def diagnosis_update(diagn_id: str, year: str | None = None, month: str | None = None, day: str | None = None,
                     obser_id: str | None = None,
                     comment_text: str | None = None,
                     file_oid: int | None = None):
    require_admin()
    y_in = None if _is_blank(year)  else _to_int(year) if isinstance(year, str)  else year
    m_in = None if _is_blank(month) else _to_int(month) if isinstance(month, str) else month
    d_in = None if _is_blank(day)   else _to_int(day) if isinstance(day, str)   else day

    with get_conn() as s:
        old = s.run("MATCH (g:Diagnosis {diagn_id:$id}) "
                    "RETURN g.diagn_year AS y, g.diagn_month AS m, g.diagn_day AS d",
                    id=diagn_id).single()
        if not old:
            raise ValueError("diagnosis not found")
        merged_y = y_in if y_in is not None else old["y"]
        merged_m = m_in if m_in is not None else old["m"]
        merged_d = d_in if d_in is not None else old["d"]
        validate_date_parts(merged_y, merged_m, merged_d, label="diagnosis date")

        sets = []
        params = {"id": diagn_id}
        if y_in is not None: sets.append("g.diagn_year=$yy"); params["yy"] = y_in
        if m_in is not None: sets.append("g.diagn_month=$mm"); params["mm"] = m_in
        if d_in is not None: sets.append("g.diagn_day=$dd");  params["dd"] = d_in
        if comment_text is not None: sets.append("g.diagn_comment_text=$txt"); params["txt"] = comment_text
        if sets:
            s.run(f"MATCH (g:Diagnosis {{diagn_id:$id}}) SET {', '.join(sets)}", **params)

        if not _is_blank(obser_id):
            s.run("""
                MATCH (g:Diagnosis {diagn_id:$id})
                OPTIONAL MATCH (g)-[r:OF_OBSERVATION]->(:Observation)
                DELETE r
                WITH g
                MATCH (o:Observation {obser_id:$oid})
                MERGE (g)-[:OF_OBSERVATION]->(o)
            """, id=diagn_id, oid=obser_id)

        if file_oid is not None:
            s.run("""
                MATCH (g:Diagnosis {diagn_id:$id})
                OPTIONAL MATCH (g)-[r:FILE]->(:Blob)
                DELETE r
                WITH g
                MATCH (b:Blob {oid:$oid})
                MERGE (g)-[:FILE]->(b)
            """, id=diagn_id, oid=file_oid)

def diagnosis_delete(diagn_id: str):
    require_admin()
    with get_conn() as s:
        s.run("MATCH (g:Diagnosis {diagn_id:$id}) DETACH DELETE g", id=diagn_id)
