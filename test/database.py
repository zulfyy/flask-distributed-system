import psycopg2 # Database PostgreSQL Port

class Database:
    serverHost = ''
    
    def __init__(self, serverHost, user='postgres', password= '',dbname = '', port = 5432):
            self.serverHost = serverHost
            self.user       = user
            self.password   = password
            self.dbname     = dbname
            self.port       = port
            self.connection = None

    def connect(self):
        try:
            self.connection = psycopg2.connect(
                 host = self.serverHost,
                 user = self.user,
                 password = self.password,
                 dbname = self.dbname,
                 port = self.port
            )
            print("Connection to Database Success!")
            return True
        except psycopg2.DatabaseError as e:
            print(f"Error when connection to server {self.serverHost}.\nError: {e}")
             


    
    
    