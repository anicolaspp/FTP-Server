import socket
import os
import platform
import sys
import threading
import uuid

class UserManager:
    def __init__(self):
        self.user = None
        self.pa = None

    def set_user(self, user):
        print user
        self.user = user

    def set_pass(self, pas):
        print pas
        self.pas = pas

    def is_valid_account(self):
        if self.user == self.pas:
            return True
        else:
            return False

class FileManager:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.current_dir = base_dir

    def get_current(self):
        return os.path.realpath(self.current_dir)

    def move_to(self, cmd):  
        chwd=cmd
        tmp = ''

        if self.current_dir == self.base_dir and chwd.strip() == '..':
            print 'Trying to abandon user base dir'
            return ''

        if chwd=='/':
            tmp = os.path.realpath(self.base_dir)
        elif chwd[0]=='/':
            tmp = os.path.join(os.path.realpath(self.base_dir), chwd[1:])
        else:
            tmp = os.path.join(os.path.realpath(self.current_dir), chwd)

        tmp = tmp.strip()

        pathTokens = tmp.split('\\')
        if pathTokens[len(pathTokens) - 1] == '..':
            tmp = '\\'.join(pathTokens[:len(pathTokens) - 2])
            print 'new tmp: ' + tmp

        print 'last token: ' + pathTokens[len(pathTokens) - 1]

        print 'trying to access to: ' + tmp

        if not os.path.isdir(os.path.realpath(tmp)):
           return ''

        self.current_dir = tmp
        return self.current_dir

    def get_dir_content(self):
        dirs = os.listdir(self.current_dir)
        result = ''
        
        for item in dirs:
            result += item + '\n'

        return result

    def create_dir(self, name):
        if name == '':
            return ''
        
        path = self.move_to(name)

        if not path == '':
            self.move_to('..')
            return ''
        else:
            path = os.path.join(self.current_dir, name)
            os.mkdir(path)
            return path

    def write_content_from_stream_to(self, fname, stream):
        fpath = os.path.join(os.path.realpath(self.current_dir), fname)

        if os.path.isfile(fpath):
            os.remove(fpath)
            
        writer = open(fpath, 'a+')
        data = None
         
        while True:
            data = stream.recv(1024)
            if not data:
                break
            else:
                writer.write(data)
        writer.close()

    def write_content_from_file_to(self, stream, fname):
        status = ''
        fpath = os.path.join(os.path.realpath(self.current_dir), fname)
        print fpath
        if not os.path.isfile(fpath):
            status = '451 File does not exist\r\n'
            print status
        else:
            reader = open(fpath, 'r+')         
            while True:
                data = reader.read(1024)
                print data
                if not data:
                    reader.close()
                    status = '226 File transmition complete\r\n'
                    break
                else:
                    stream.send(data)

            stream.send('\r\n')
        return status

    def delete_file(self, fname):
        fpath = os.path.join(os.path.realpath(self.current_dir), fname)

        if os.path.isfile(fpath):
            os.remove(fpath)
            return True
        else:
            return False


class UserFtpThread (threading.Thread):
    def __init__(self, (conn, addr), clients):
        self.conn = conn
        self. addr = addr
        self.acctManager = UserManager()
        self.fmanager = FileManager(os.path.dirname(os.path.realpath(__file__)))
        self.data_socket = None
        self._stop = threading.Event()
        self.clients = clients
        self.client_id = uuid.uuid1()
        self.clients.append((self.client_id, addr, self))
        
        threading.Thread.__init__(self)

    def stop(self):
        try:
            self.conn.send('221 Closing Connection\r\n')
            self.conn.close()
            self._stop.set()
        except:
            pass

    def run(self):
        try:
            self.conn.send('220 Welcome to nick server\r\n')
            self.execute()
        except Exception as ex:
            print 'Exception raised',
            print ex

        self.stop()

    def validate_user(self, acct):
        return acct.is_valid_account()

    def run_validation(cmd_runner):
        def runner_wrapper(self, *args, **kwargs):
            if self.validate_user(self.acctManager):
                return cmd_runner(self, *args, **kwargs)
            else:
                self.conn.send('530 Need Auth\r\n')
        return runner_wrapper
        
    def user_runner(self, user):
        self.acctManager.set_user(user)
        self.conn.send('331 Need pass\r\n')

    def pass_runner(self, pasw):
        self.acctManager.set_pass(pasw)
        if self.acctManager.is_valid_account():
            self.conn.send('230 Pass OK\r\n')
        else:
            self.conn.send('530 Incorrect Pass\r\n')

    def port_runner(self, addr, port):
        self.data_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.data_socket.connect((addr, port))
        self.conn.send('200 Get Port\r\n')

    @run_validation
    def xpwd_runner(self):
        self.conn.send('257 Current Directory: \"%s\"\r\n' % self.fmanager.current_dir)

    @run_validation
    def list_runner(self):
        self.conn.send('150 Listing Directory Content\r\n')

        result = self.fmanager.get_dir_content()
        self.data_socket.send(result)
        self.data_socket.close()

        self.conn.send('226 Directory send OK\r\n')

    @run_validation
    def cwd_runner(self, path):
        cd = self.fmanager.move_to(path)

        if cd == '':
            self.conn.send('550 ' + path +': No such file or directory\r\n')
        else:
            print 'current dir: ' + cd
            self.conn.send('250 OK.\r\n')

    @run_validation
    def stor_runner(self, fname):
        self.conn.send('150 About to start getting data\r\n')
                
        self.fmanager.write_content_from_stream_to(fname, stream=self.data_socket)
        self.data_socket.close()

        self.conn.send('226 Transfer complete\r\n')

    @run_validation
    def dele_runner(self, fname):
        if self.fmanager.delete_file(fname):
            self.conn.send('250 file removed\r\n')
        else:
            self.conn.send('450 removal failed\r\n')

    @run_validation
    def mkd_runner(self, dirName):
        result = self.fmanager.create_dir(dirName)

        if result == '':
            self.conn.send('550 creation fail\r\n')
        else:
            self.conn.send('250 ' + result + '\r\n')

    @run_validation
    def rert_runner(self, fname):
        self.conn.send('150 Opening Transmission Stream\r\n')

        
        status = self.fmanager.write_content_from_file_to(self.data_socket, fname)
        self.data_socket.close()
        self.conn.send(status)

    def quit_runner(self):
        self.conn.send('221 Closing Connection\r\n')

        lock = threading.Lock()
        lock.acquire()
        self.clients.remove((self.client_id, self.addr, self))
        lock.release()
                
        self._stop.set()
          
    def execute(self):
        while True:      
            cmd = self.conn.recv(256)

            if not cmd:
                break

            if cmd[:4].strip().upper() == 'USER':
                self.user_runner(cmd[5:])
                
            elif cmd[:4].strip().upper() == 'PASS':
                self.pass_runner(cmd[5:])
                
            elif cmd[:4].strip().upper() == 'XPWD':
                self.xpwd_runner()
  
            elif cmd[:4].strip().upper() == 'PORT':
                add = cmd[5:].split(',')[:4]
                add = add[0]+'.'+add[1]+'.'+add[2]+'.' +add[3]
                port = cmd[5:].split(',')[4:]
                port = int(port[0]) * 256 + int(port[1])

                self.port_runner(add, port)

            elif cmd[:4].strip().upper() == 'LIST' or cmd[:4].strip().upper() == 'NLST':
               self.list_runner()

            elif cmd[:3].strip().upper() == 'CWD':
                self.cwd_runner(cmd[4:].strip())

            elif cmd[:4].strip().upper() == 'STOR':
                fname = cmd[5:].strip()
                self.stor_runner(fname)
                
            elif cmd[:4].strip().upper() == 'DELE':
                self.dele_runner(cmd[5:].strip())

            elif cmd[:4].strip().upper() == 'XMKD' or cmd[:3].strip().upper() == 'MKD':
                self.mkd_runner(cmd.split(' ')[1].strip())
                
            elif cmd[:4].strip().upper() == 'RETR':
                self.rert_runner(cmd[5:].strip())      
                
            elif cmd[:4].strip().upper() == 'QUIT':
              self.quit_runner()  

   
class ServerThread (threading.Thread):
    def __init__(self):
        self.ms = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.ms.bind(('', local_port))
        self.clients = []
        threading.Thread.__init__(self)

    def run(self):
        print 'Server started on ' + socket.gethostbyname(socket.gethostname()) +':'+str(local_port)
        self.ms.listen(5)
        
        while True:
            print 'Waiting from clients\n'

            conn, addr = self.ms.accept()
            newUserConnection = UserFtpThread((conn, addr), self.clients)
            newUserConnection.start()

    def stop(self):
        print 'Closing open client connections'
        
        for item in self.clients:
            item[2].stop()
            
        self.ms.close()
        

if __name__ =='__main__':
    
    print 'Starting nick server'

    args = sys.argv
    print args
    local_port = 2123

    if len(args) < 2:
        print 'No port number passed. Programm will try to use port# ' + str(local_port)
    else:
        local_port = int(args[1])

    server = ServerThread()
    server.start()

    while True:
        cmd = raw_input('Type q to stop server or clients to get active clients\n')
        if cmd == 'q':
            server.stop()
            print 'Server stoped'
            exit()
        else:
            if cmd == 'clients':
                print 'Connected Clients: ',
                print server.clients
            

    


        
