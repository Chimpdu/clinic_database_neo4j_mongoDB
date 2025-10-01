# What does this repo do?
This repo simulates a clinic database with messaging function where doctors and patients can communicate. <br><br>
Data of the clinic, department, doctor, patient, appointment, observation and diagnosis and their relationships are stored in a graph database (Neo4J) and the messages between doctors and patients are stored in a document database (MongoDB)

# How does the code work?
## Bootstrapping Neo4J
By running "bootstrap_neo4j.py", it creates a database using the Neo4J install on your machine. 

You are  given two default accounts after bootstraping:
### username: admin password: admin    (admin account, can edit data)
### username: user password: user123   (normal user, view data only)

By using the admin account, you can perform full CRUD opertions on the data. 
## Auto create accounts for inserted doctors and patients
Every time admin user inserts a doctor, the system would auto create a admin account for that doctor with the following default setup:

### username/password: "d" + {doctor's personnumer}

Similarly, a normal user account will be auto created for a patient when a patient is inserted. In addition, patients are further restricted that they cannot view the data stored in the database, but can view/send messages from/to their doctors and manage their account settings.
### username/password: "p" + {patient's personnumer}

## Change account settings

By logging into the app using their default credientials, every user could change their username and password.

## Messaging between doctor's and patients
By logging into the app either as a doctor or as a patient, you will see a messaging button on the main interface. <br><br>The messaging function allows the doctor to message patients that are assigned to him/her. Same goes for the patient. There will be a dropdown list showing allowed contacts. <br><br>The messages can be both text and files. and willed be saved in MongoDB. All files submitted to Neo4J or Mongo databases are currently saved in the "files" folder at the same level of the code files.<br><br> The messages sent are only visible to its sender and receiver in the messaging window.
# How to run?
1. Install and setup Neo4J and MongoDB on your machine. Make sure they are running.
2. Download dependencies in requirements.txt
3. Run bootstrap_neo4j.py and provide your password for Neo4J. Credentials are save in ./neo4j_app/credentials.json (include in the .gitignore)
4. Run login.py 
5. Log in using the default admin or normal user account. Insert data using admin account.
6. If you have inserted doctors and patients data, you could login as these roles using their default account. You can then change account settings and/or message to doctors or patients.


### pip install neo4j 
### pip install sv_ttk
### pip install pymongo
### python3 bootstrap_neo4j.py
### python3 login.py
