The data are stored in graph database neo4j and messaging between doctor and patients are saved in mongoDB

First, download dependency from requirement.txt

Second, run bootstrap_neo4j.py to create the database. Login neo4j by providing your password in the commandline.

Third, run login.py to login Default "admin" password "admin" default normal user "user1" password "user123"

The files uploaded are stored in the "files" directory.
Credentials are save in credentials.json (include in the .gitignore)
How to run:

### pip install neo4j 
### pip install sv_ttk
### python3 bootstrap_neo4j.py
### python3 login.py