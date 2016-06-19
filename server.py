#!/usr/bin/env python
# Set this variable to "threading", "eventlet" or "gevent" to test the
# different async modes, or leave it set to None for the application to choose
# the best option based on available packages.
#async_mode = 'threading'
#async_mode = 'eventlet'
async_mode = None
if async_mode is None:
    try:
        import eventlet
        async_mode = 'eventlet'
    except ImportError:
        pass

    if async_mode is None:
        try:
            from gevent import monkey
            async_mode = 'gevent'
        except ImportError:
            pass

    if async_mode is None:
        async_mode = 'threading'

    print('async_mode is ' + async_mode)

# monkey patching is necessary because this application uses a background
# thread
if async_mode == 'eventlet':
    import eventlet
    eventlet.monkey_patch()
elif async_mode == 'gevent':
    from gevent import monkey
    monkey.patch_all()


import time
from threading import Thread, Lock
from flask import Flask, render_template, session, request
from flask_socketio import SocketIO, emit, join_room, leave_room,close_room, rooms, disconnect
import sys
import glob
import serial
import json


import csv

#Version 2.7 or Above?
if sys.version_info[0] >2:
    version3 = True
    kwargs = {'newline':''}
else:
    version3 = False 
    kwargs = {}



##import logging
##log = logging.getLogger('werkzeug')
##log.setLevel(logging.ERROR)




serialConnected = False #global flag for whether or not the serial port should be connected
serialPort =0  # (init value is 3...junk) contains serial port object when in use...touching protected by serialLock below
serialLock = Lock() #serial permission lock (protects shared resource of serial port)
print (serialLock)

#Taken from here on StackExchange: http://stackoverflow.com/questions/12090503/listing-available-com-ports-with-python
#Want to give credit where credit is due!
def serial_ports():
    if sys.platform.startswith('win'):
        ports = ['COM%s' % (i + 1) for i in list(range(256))]
    elif sys.platform.startswith('linux') or sys.platform.startswith('cygwin'):
        # this excludes your current terminal "/dev/tty"
        ports = glob.glob('/dev/tty[A-Za-z]*')
    elif sys.platform.startswith('darwin'):
        ports = glob.glob('/dev/tty.*')
    else:
        raise EnvironmentError('Unsupported platform')

    result = []
    for port in ports:
        try:
            #print("checking port "+port)
            s = serial.Serial(port)
            #print("closing port "+port)
            s.close()
            result.append(port)
        except (OSError, serial.SerialException):
            pass
    return result
#-------------------

#serial variables:

serialselection = ''
baudselection = 115200

mcuMessage = []

Kp = 0.0
Kd = 0.0
Ki = 0.0
direct = 0.0
desired = 0.0
alternate = 0.0


#Start up Flask server:
app = Flask(__name__, template_folder = './',static_url_path='/static')
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, async_mode = async_mode)
thread = None

#csv variables:
global csv_default
global csv_recent
global current
global archive
#variable which determines whether a csv is being generated or not.
csv_yn = False  #start out not writing csv files
csvLock = Lock()

keepRunning = True #set to True for default


def serialThread():
    print ("Starting serial background thread.")
    global serialLock
    global csvLock
    global serialPort
    global csv_default
    global csv_recent
    while True:
        #print (serialConnected)
        if serialConnected:
            print ("Starting to read serial subthread")
            while serialConnected:
                serialLock.acquire()
                try:
                    bytesThere = serialPort.inWaiting()
                except:
                    print ("Failed serial check")
                    bytesThere = 0
                    
                #print (bytesThere)
                if bytesThere == 12:
                    #print ('message')
                    try:
                        b = serialPort.read(bytesThere)
                        #print (b)
                        out = messageRead(b)
                        #print (out)
                    except:
                        out = None
                        print ("Serial Read Error")
                    #serialLock.release()
                    if out != None:
                        #print (out)
                        #print (type(out))
                        try:
                            socketio.emit('note',out,broadcast =True)
                        except:
                            print ("failed socket")
                        if csv_yn:
                            temp_time = [time.time()]
                            params = [Kp,Kd,Ki,direct,desired,alternate]
                            csvLock.acquire()
                            csv_default.writerow(temp_time+out+params)
                            csv_recent.writerow(temp_time+out+params)
                            csvLock.release()
                elif bytesThere > 12:
                    try:
                        serialPort.flushInput()
                    except:
                        print ("failure to flush input")
                serialLock.release()
                time.sleep(0.01)
            print ("Stopping serial read. Returning to idle state")
        time.sleep(0.01)



#runtime variables...
def messageRead(buff):
    #print ("Reading message!")
    #print (buff)
    if not version3:
        newb = buff
        buff = [ord(q) for q in newb] #converts yucky binary/string abominations of python 2.* into list of ascii numbers essentially...not issue in 3
    mcuMessage=list(range(12))
    #for x in buff:
        #print (x)
    if buff[0] == 0 and buff[11] == 255: #likely correct message
        #print ('message correct!')
        errorF = False
        mcuMessage[0] = buff[0]
        mcuMessage[11] = buff[11]
        for i in range(1,11):
            bufI = buff[i]
            if bufI ==0 or bufI == 255:
                errorF = True;
            mcuMessage[i] = bufI
        if not errorF:
            #print ("about to send a 'note'")
            #print (mcuMessage)
            #emit('note',mcuMessage,broadcast=True)
            return mcuMessage
    return None           


@app.route('/')
def index():
    global thread
    print ("A user connected")
    if thread is None:
        thread = Thread(target=serialThread)
        thread.daemon = True
        thread.start()
    return render_template('index.html')

@socketio.on('connect')
def test_connect():
    print ('hey someone connected')
    ports = serial_ports() #generate list of currently connected serial ports 
    print (ports)
    newb=[]
    for p in ports:
        newb.append({"comName": p})
    print (json.dumps(newb))
    #emit('serial list display', {'data': ports}) #emit socket with serial ports in it
    emit('serial list display', newb) #emit socket with serial ports in it
    #emit('my response', {'data': 'Connected'}) 

@socketio.on('disconnect')
def test_disconnect():
    global csv_yn
    global csvLock
    emit('serial disconnect request',broadcast=True)
    csv_yn = 0
    #if current is not None and archive is not None:
    csvLock.acquire()
    try:
        current.close()
        archive.close()
    except NameError:
        pass #if didn't exist yet, don't try...
    csvLock.release()
    print('Client disconnected. Hopefully that was for the best.')

def writeUpdates(tag,val):
    global serialPort
    global serialLock
                
    string_to_write = tag+' %0.2f\n' %(float(val))
    if serialConnected:
        serialLock.acquire() #claim serial resource
        if version3:
            serialPort.write(bytes(string_to_write,'UTF-8'))
        else:
            serialPort.write(string_to_write)
        serialLock.release() #release serial resource back out into big scary world
    else:
        print ("Change in %s to value %s not written since no live serial comm exists yet" %(tag,val))


# Specs
@socketio.on('serial select')
def action(port):
    global serialselection
    print ('serial port changed to %s' %(port))
    serialselection = port
    
@socketio.on('baud select')
def action(baud):
    global baudselection
    print ('baud changed to %s' %(baud))
    baudselection = baud

@socketio.on('csv state')
def csver(csv_val):
    global csv_default
    global csv_recent
    global current
    global archive
    global csv_yn
    global csvLock
    if int(csv_val) == 0:
        print('closing csv files')
        csv_yn = 0
        csvLock.acquire()
        try:
            current.close()
            archive.close()
        except NameError:
            pass #did not exist yet...totes fine
        csvLock.release()
    else: #do other thing
        print('Trying opening csv files up!')
        #current = open('./csv_files/current.csv',"w",encoding='utf8',newline='')
        #archive = open('./csv_files/'+str(int(time.time()))+'.csv',"w",encoding='utf8',newline='')
        try:
            current = open('./csv_files/current.csv',"w",**kwargs)
            archive = open('./csv_files/'+str(int(time.time()))+'.csv',"w",**kwargs)
            csv_default = csv.writer(archive)
            csv_recent = csv.writer(current)
            csv_yn = 1
            print ('CSV File Open successful')
        except:
            print("Failed to open CSV Files")
                
    


@socketio.on('serial connect request')
def connection():
    global serialConnected
    global serialPort
    global serialLock
    print ('Trying to connect to: ' + serialselection + ' ' + str(baudselection))
    print (serialLock)
    print (serialConnected)
    try:
        serialLock.acquire()
        print ("Lock acquired")
        serialPort = serial.Serial(serialselection, int(baudselection))
        print ('SerialPort')
        print ('Connected to ' + str(serialselection) + ' at ' + str(baudselection) + ' BAUD.')
        emit('serial connected', broadcast=True) #tells page to indicate connection (in button)
        serialPort.flushInput()
        serialPort.flushOutput()
        writeUpdates('P',Kp)
        writeUpdates('I',Ki)
        writeUpdates('D',Kd)
        writeUpdates('O',direct)
        writeUpdates('A',desired)
        writeUpdates('T',alternate)
        serialLock.release()
        serialConnected = True #set global flag
    except:
        print ("Failed to connect with "+str(serialselection) + ' at ' + str(baudselection) + ' BAUD.')



@socketio.on('serial disconnect request')
def discon():
    global serialConnected
    global serialLock
    global serialPort
    print ('Trying to disconnect...')
    serialLock.acquire()
    serialPort.close()
    serialLock.release()
    serialConnected = False 
    emit('serial disconnected',broadcast=True)
    print ('Disconnected...good riddance' )

@socketio.on("disconnected")
def ending_it():
    print ("We're done")

@socketio.on('note')
def thing(stuff):
    print ('socket_sent!')
    print (stuff)

@socketio.on('change Kp')
def action(Kin):
    global Kp
    Kp = Kin
    writeUpdates('P',Kp)

@socketio.on('change Ki')
def action(Kin):
    global Ki
    Ki = Kin 
    writeUpdates('I',Ki)

@socketio.on('change Kd')
def action(Kin):
    global Kd
    Kd = Kin 
    writeUpdates('D',Kd)

@socketio.on('change direct')
def action(dir):
    global direct
    direct = dir
    writeUpdates('O',direct)

@socketio.on('change desired')
def action(des):
    global desired
    desired = des
    writeUpdates('A',desired)
    
@socketio.on('change state')
def action(alt):
    global alternate
    if alt == 1:
        print ('Desired Angle changed to alternating at +/- %0.2f ' %(float(desired)))
    else:
        print ('Desired Angle changed to fixed at %0.2f' %(float(desired)))
    alternate = alt
    writeUpdates('T',alternate)





if __name__ == '__main__':
    socketio.run(app, port=3000, debug=True)


