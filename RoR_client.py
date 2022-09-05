import sys, struct, threading, socket, random, time, string, os, os.path, math, copy, logging, queue, re, TruckToName, hashlib
import pickle # needed for recording
from RoRnet import *
import asyncio

def b(s, encoding="utf-8"):
    """ Convert `s` to bytes. """
    if isinstance(s, bytes):
        return s
    else:
        return s.encode(encoding=encoding)

def s(b, encoding="utf-8"):
    """ Convert `b` to str. """
    if isinstance(b, str):
        return b
    else:
        return b.decode(encoding=encoding)


COLOUR_BLACK    = "#000000"
COLOUR_GREY     = "#999999"
COLOUR_RED      = "#FF0000"
COLOUR_BLUE     = "#FFFF00"
COLOUR_WHITE    = "#FFFFFF"
COLOUR_CYAN     = "#00FFFF"
COLOUR_BLUE     = "#0000FF"
COLOUR_GREEN    = "#00FF00"
COLOUR_MAGENTA  = "#FF00FF"
COLOUR_COMMAND  = "#941e8d"
COLOUR_NORMAL   = "#FFFFFF"
COLOUR_WHISPER  = "#967417"
COLOUR_SCRIPT   = "#32436f"

playerColours = [
        "#00CC00",
        "#0066B3",
        "#FF8000",
        "#FFCC00",
#       "#330099",
#       "#990099",
        "#CCFF00",
        "#FF0000",
        "#808080",
        "#008F00",
#       "#00487D",
        "#B35A00",
        "#B38F00",
#       "#6B006B",
        "#8FB300",
        "#B30000",
        "#BEBEBE",
        "#80FF80",
        "#80C9FF",
        "#FFC080",
        "#FFE680",
        "#AA80FF",
        "#EE00CC",
        "#FF8080",
        "#666600",
        "#FFBFFF",
        "#00FFCC",
        "#CC6699",
        "#999900"
];

def getTruckName(filename):
    if filename in TruckToName.list:
        return TruckToName.list[filename]
    return re.sub(rb'''([a-z0-9]*\-)?((.*)UID\-)?(.*)\.(truck|car|load|airplane|boat|trailer|train|fixed)''', rb'''\4''', filename.lower())

def getTruckType(filename):
    return filename.split(b'.').pop().lower()

def getTruckInfo(filename):
    return {
            'type': getTruckType(filename),
            'name': getTruckName(filename),
            'file': filename,
    }

class interruptReceived(Exception):
    pass

class DataPacket:
    source=0
    command=0
    streamid=0
    size=0
    data=0
    time=0
    def __init__(self, command, source, streamid, size, data):
        self.source = source
        self.command = command
        self.streamid = streamid
        self.size = size
        self.data = data
        self.time = time.time()

#####################
# STREAM MANAGEMENT #
#####################
"""
This class stores information about users and streams.
        - D (dictionary)
           |- <uid> (user_t)
           |   |- user (user_info_t)
           |   |   |- uniqueID
           |   |   |- username
           |   |   |- usertoken
           |   |   |- serverpassword
           |   |   |- language
           |   |   |- clientname
           |   |   |- clientversion
           |   |   |- clientGUID
           |   |   |- sessiontype
           |   |   |- sessionoptions
           |   |   |- authstatus
           |   |   |- slotnum
           |   |   \- colournum
           |   |
           |   |- stream (dictionary)
           |   |   |- <streamID> (stream_info_t)
           |   |   |   |- name
           |   |   |   |- fileExt
           |   |   |   |- type
           |   |   |   |- status
           |   |   |   |- origin_sourceid
           |   |   |   |- origin_streamid
           |   |   |   |- bufferSize
           |   |   |   |- regdata
           |   |   |   |- refpos
           |   |   |   \- rot
           |   |   |
           |   |   \- <...>
           |   |
           |   \- stats (user_stats_t)
           |       |- onlineSince
           |       |- distanceDriven
           |       |- distanceSailed
           |       |- distanceWalked
           |       |- distanceFlown
           |       |- currentStream
           |       |- characterStreamID
           |       \- chatStreamID
           |
           \- <...>
"""
class user_t:
    def __init__(self, user_info):
        self.user = user_info
        self.stream = {}
        self.stats = user_stats_t()

def isPointIn2DSquare(p, s):
    ABP = triangleAreaDouble(s[0], s[1], p)
    BCP = triangleAreaDouble(s[1], s[2], p)
    CDP = triangleAreaDouble(s[2], s[3], p)
    DAP = triangleAreaDouble(s[3], s[0], p)
    return ( ABP >= 0 and BCP >= 0 and CDP >= 0 and DAP >= 0 ) or ( ABP < 0 and BCP < 0 and CDP < 0 and DAP < 0 )

def triangleAreaDouble(a, b, c):
    return (c.x*b.y-b.x*c.y) - (c.x*a.y-a.x*c.y) + (b.x*a.y-a.x*b.y)

def squaredLengthBetween2Points(a, b):
    return ((a.x-b.x)**2 + (a.y-b.y)**2 + (a.z-b.z)**2)

def lengthBetween2Points(a, b):
    return math.sqrt((a.x-b.x)**2 + (a.y-b.y)**2 + (a.z-b.z)**2)


class streamManager:

    def __init__(self):
        self.D = {}
        self.globalStats = {
                'connectTime': time.time(),
                'distanceDriven': float(0),
                'distanceSailed': float(0),
                'distanceWalked': float(0),
                'distanceFlown': float(0),
                'usernames': set(),
                'userCount': 0,
                'connectTimes': list()
        }

        # Add the server itself as a client (hacky hack)
        u = user_info_t()
        u.username = "server"
        u.uniqueID = -1
        u.authstatus = AUTH_BOT
        self.addClient(u)

    def addClient(self, user_info):
        if not user_info.uniqueID in self.D:
            self.D[user_info.uniqueID] = user_t(user_info)
            self.globalStats['usernames'].add(user_info.username)
            self.globalStats['userCount'] += 1
        else:
            self.D[user_info.uniqueID].user = user_info

    def delClient(self, uid):
        if uid in self.D:
            self.globalStats['distanceDriven'] += self.D[uid].stats.distanceDriven
            self.globalStats['distanceSailed'] += self.D[uid].stats.distanceSailed
            self.globalStats['distanceWalked'] += self.D[uid].stats.distanceWalked
            self.globalStats['distanceFlown']  += self.D[uid].stats.distanceFlown
            self.globalStats['connectTimes'].append(time.time()-self.D[uid].stats.onlineSince)
            del self.D[uid]

    # s: stream_info_t
    def addStream(self, s):
        if s.origin_sourceid in self.D:
            s.fileExt = getTruckType(s.name)
            self.D[s.origin_sourceid].stream[s.origin_streamid] = s

            if s.type == TYPE_CHARACTER:
                self.setCharSID(s.origin_sourceid, s.origin_streamid)
            elif s.type == TYPE_CHAT:
                self.setChatSID(s.origin_sourceid, s.origin_streamid)

    def delStream(self, uid, sid):
        if uid in self.D and sid in self.D[uid].stream:
            if self.D[uid].stream[sid].origin_streamid == self.D[uid].stats.characterStreamID:
                self.D[uid].stats.characterStreamID = -1
            elif self.D[uid].stream[sid].origin_streamid == self.D[uid].stats.chatStreamID:
                self.D[uid].stats.chatStreamID = -1
            del self.D[uid].stream[sid]

    def setPosition(self, uid, sid, pos):
        if uid in self.D and sid in self.D[uid].stream:

            if pos.x<1.0 and pos.y<1.0 and pos.z<1.0 and pos.x>-1.0 and pos.y>-1.0 and pos.z>-1.0:
                self.D[uid].stream[sid].refpos = pos
                return
            pos2 = self.D[uid].stream[sid].refpos
            if pos2.x<1.0 and pos2.y<1.0 and pos2.z<1.0 and pos2.x>-1.0 and pos2.y>-1.0 and pos2.z>-1.0:
                self.D[uid].stream[sid].refpos = pos
                return

            dist = lengthBetween2Points(pos, self.D[uid].stream[sid].refpos)
            if dist<10.0:
                if self.D[uid].stream[sid].type == TYPE_CHARACTER:
                    self.D[uid].stats.distanceWalked += dist
                elif self.D[uid].stream[sid].fileExt == b'truck':
                    self.D[uid].stats.distanceDriven += dist
                elif self.D[uid].stream[sid].fileExt == b'airplane':
                    self.D[uid].stats.distanceFlown += dist
                elif self.D[uid].stream[sid].fileExt == b'boat':
                    self.D[uid].stats.distanceSailed += dist
            else:
                #print "large distance jump detected: %f" % dist
                #print pos
                #print self.D[uid].stream[sid].refpos
                self.D[uid].stream[sid].refpos = pos

    def getPosition(self, uid, sid = -1):
        if sid == -1:
            return self.getCurrentStream(uid).refpos
        elif uid in self.D and sid in self.D[uid].stream:
            return self.D[uid].stream[sid].refpos
        else:
            return vector3()

    def setRotation(self, uid, sid, rot):
        if uid in self.D and sid in self.D[uid].stream:
            self.D[uid].stream[sid].rot = rot

    def getRotation(self, uid, sid):
        if uid in self.D and sid in self.D[uid].stream:
            return self.D[uid].stream[sid].rot
        else:
            return vector4()

    def setCurrentStream(self, uid_person, uid_truck, sid):
        if uid_person in self.D and uid_truck in self.D and sid in self.D[uid_truck].stream:
            self.D[uid_person].stats.currentStream = {'uniqueID': uid_truck, 'streamID': sid}
            if sid != self.D[uid_person].stats.characterStreamID or uid_person != uid_truck:
                self.setPosition(uid_person, self.D[uid_person].stats.characterStreamID, vector3())

    def getCurrentStream(self, uid):
        if uid in self.D:
            if self.D[uid].stats.currentStream['uniqueID'] in self.D and self.D[uid].stats.currentStream['streamID'] in self.D[self.D[uid].stats.currentStream['uniqueID']].stream:
                return self.D[self.D[uid].stats.currentStream['uniqueID']].stream[self.D[uid].stats.currentStream['streamID']]
        return stream_info_t()

    def setCharSID(self, uid, sid):
        if uid in self.D and sid in self.D[uid].stream:
            self.D[uid].stats.characterStreamID = sid

    def getCharSID(self, uid):
        if uid in self.D:
            return self.D[uid].stats.characterStreamID
        else:
            return -1

    def setChatSID(self, uid, sid):
        if uid in self.D and sid in self.D[uid].stream:
            self.D[uid].stats.chatStreamID = sid

    def getChatSID(self, uid):
        if uid in self.D:
            return self.D[uid].stats.chatStreamID
        else:
            return -1

    def getOnlineSince(self, uid):
        if uid in self.D:
            return self.D[uid].stats.onlineSince
        else:
            return 0.0

    def countClients(self):
        return len(self.D)-1 # minus one because, internally, we consider the server to be a user

    def countStreams(self, uid):
        if uid in self.D:
            return len(self.D[uid].stream)
        else:
            return 999999

    def getUsernameColoured(self, uid):
        try:
            return "%s%s%s" % (playerColours[self.D[uid].user.colournum], self.D[uid].user.username, COLOUR_WHITE)
        except:
            return "%s%s" % (self.D[uid].user.username, COLOUR_WHITE)

    def getUsername(self, uid):
        if uid in self.D:
            return self.D[uid].user.username
        elif not uid is None:
            return "unknown(%d)" % (uid)
        else:
            return "unknown(None)"

    def getAuth(self, uid):
        if uid in self.D:
            return self.D[uid].user.authstatus
        else:
            return AUTH_NONE

    def getClientName(self, uid):
        if uid in self.D:
            return self.D[uid].user.clientname
        else:
            return "unknown(%d)" % (uid)

    def getClientVersion(self, uid):
        if uid in self.D:
            return self.D[uid].user.clientversion
        else:
            return "0.00"

    def getLanguage(self, uid):
        if uid in self.D:
            return self.D[uid].user.language
        else:
            return "xx_XX"

    def userExists(self, uid):
        return uid in self.D

    def getSessionType(self, uid):
        if uid in self.D:
            return self.D[uid].user.sessiontype
        else:
            return ""

    def getStreamData(self, uid, sid):
        if uid in self.D and sid in self.D[uid].stream:
            return self.D[uid].stream[sid]
        else:
            return stream_info_t()

    def getUserData(self, uid):
        if uid in self.D:
            return self.D[uid].user
        else:
            return user_info_t()

    def getStats(self, uid = None):
        if uid is None:
            return self.globalStats
        elif uid in self.D:
            return self.D[uid].stats
        else:
            return user_stats_t()

    def getUIDByName(self, name):
        for p in self.D.values():
            if p.user.username==name:
                return p.user.uniqueID
        return 0


    def clear(self):
        self.D.clear()

    def getOnlineUserIdentifiers(self):
        return list(self.D.keys())

    def getStreamIdentifiers(self, uid):
        if uid in self.D:
            return list(self.D[uid].stream.keys())
        else:
            return []

class Discord_Layer:

    def __init__(self, streamManager, main, ID):
        # Few things were inherited from the old IRC layer
        self.sm = streamManager
        self.main = main
        self.ID = ID
        self.channelID = self.main.settings.getSetting('RoRclients', self.ID, 'discordchannel')
        self._stripRoRColoursReg =  re.compile( '(#[0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F][0-9A-F])')

    # internal!
    # Strips RoR colour codes out of a message
    def __stripRoRColours(self, str):
        return self._stripRoRColoursReg.sub('', str)

    # queue to Discord client
    def __send(self, msg, prefix):
        channel = self.main.get_channel(int(self.channelID))
        asyncio.run_coroutine_threadsafe(channel.send("[%s] %s" % (prefix, msg)), self.main.loop)

    # [chat] <username>: hi
    def sayChat(self, msg, uid):
        self.__send("%s: %s" % (self.sm.getUsername(uid), self.__stripRoRColours(msg)), "chat")

    # [chat] <username>: hi
    def sayLikeChat(self, msg, username):
        pass

    # [chat] <username>: hi
    def sayPrivChat(self, msg, uid):
        pass

    # [game] <username> (<language>) joined the server, using <version>
    def sayJoin(self, uid):
        self.__send("%s (%s) joined the server, using %s %s." % (self.sm.getUsername(uid),  s(self.sm.getLanguage(uid)), s(self.sm.getClientName(uid)), s(self.sm.getClientVersion(uid))), "game")

    # [game] <username> left the server
    def sayLeave(self, uid):
        self.__send("%s left the server." % (self.sm.getUsername(uid)), "game")

    # [error] <msg>
    def sayError(self, msg):
        self.__send(msg, "errr")

    # [warn] <msg>
    def sayWarning(self, msg):
        self.__send(msg, "warn")

    # [info] <msg>
    def sayInfo(self, msg):
        self.__send(msg, "info")

    # [game] <msg>
    def sayGame(self, msg):
        self.__send(msg, "game")

    # [dbug] <msg>
    def sayDebug(self, msg):
        self.__send(msg, "dbug")

    # [game] <username> is now driving a <truckname> (streams: <number of streams>/<limit of streams>)
    def sayStreamReg(self, uid, stream):
        truckinfo =  getTruckInfo(stream.name);
        invalid = self.main.validate(s(truckinfo['file']))
        if invalid:
            self.sayInfo("User **%s** with uid **%s** has spawned a **%s** which is a banned vehicle." % (self.sm.getUsername(uid), uid, s(truckinfo['file'])))
            self.main.queueKick(self.channelID, int(uid))
        else:
            self.__send("%s is now driving a %s  (**%s**)." % (self.sm.getUsername(uid), s(truckinfo['name']), s(truckinfo['file'])), "game")

    # [game] <username> is no longer driving <truckname> (streams: <number of streams>/<limit of streams>)
    def sayStreamUnreg(self, uid, sid):
        pass

    def playerInfo(self, uid):
        pass

    def globalStats(self):
        def s60(x, y):
            if y<60:
                return x+1
            else:
                return x

        s = self.sm.getStats()

        # the average time that a player stays
        averageTime = (sum(s['connectTimes'])/s['userCount'])/60

        # Amount of players that left within 1 minutes after joining
        playerPeek = 0
        for connectTime in s['connectTimes']:
            if connectTime < 60:
                playerPeek += 1

        self.__send("Since %s, we've seen %d players with %d unique usernames." % (time.ctime(s['connectTime']), s['userCount'], len(s['usernames'])), "info")
        self.__send("A player stays on average %.2f minutes, but %d players (%.2f%%) left in less than one minute." % (averageTime, playerPeek, (float(playerPeek)/float(s['userCount']))*100), "info")
        self.__send("In total, our players drove %.2f meters, flown %.2f meters, sailed %.2f meters and walked %.2f meters." % (float(s['distanceDriven']), float(s['distanceFlown']), float(s['distanceSailed']), float(s['distanceWalked'])), "info")
        self.__send("On average, per player: %.2f driven, %.2f flown, %.2f sailed and %.2f walked." % (float(s['distanceDriven'])/float(s['userCount']), float(s['distanceFlown'])/float(s['userCount']), float(s['distanceSailed'])/float(s['userCount']), float(s['distanceWalked'])/float(s['userCount'])), "info")

#####################
#  SOCKET FUNCTIONS #
#####################
# This class does all communication with the RoR server
# This is the class you'll need to make your own bot (together with DataPacket, the streamManager and the RoRnet file)
class RoR_Connection:
    def __init__(self, logger, streamManager):
        self.socket = None
        self.logger = logger
        self.sm = streamManager
        self.runCondition = 1
        self.streamID = 10 # streamnumbers under 10 are reserved for other stuff
        self.headersize = struct.calcsize('IIII')
        self.uid = 0
        self.receivedMessages = queue.Queue()
        self.netQuality = 0
        self.connectTime = 0

    def isConnected(self):
        return (self.socket != None)

    # Knock, knock - Who's there? - The Master Server! - Really? - No, but we pretend to be one :)
    # Useful to check if a server is online and to get the protocol version of the server.
    def knockServer(self, host, port):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except socket.error as msg:
            sock = None
            #print "Couldn't create socket."
            return None

        sock.settimeout(2)

        try:
            sock.connect((u"%s" % host, port))
        except socket.error as msg:
            sock.close()
            sock = None
            #print "Couldn't connect to server %s:%d" % (host, port)
            return None

        if sock is None:
            return None

        # send hello
        data = "MasterServer"
        try:
            sock.send(struct.pack('IIII'+str(len(data))+'s', MSG2_HELLO, 5000, 0, len(data), str(data)))
        except Exception as e:
            #print 'sendMsg error: '+str(e)
            return None


        # receive answer
        data = ""
        tmp = ""
        errorCount = 0
        try:
            while len(data)<self.headersize:
                try:
                    tmp = sock.recv(self.headersize-len(data))
                except socket.timeout:
                    continue

                # unfortunately, we have to do some stupid stuff here, to avoid infinite loops...
                if not tmp:
                    errorCount += 1
                    if errorCount > 3:
                        # lost connection
                        #print "Connection error #ERROR_CON005"
                        break
                    continue
                else:
                    data += tmp

            if not data or errorCount > 3:
                # lost connection
                #print "Connection error #ERROR_CON008"
                sock.close()
                sock = None
                return None

            (command, source, streamid, size) = struct.unpack('IIII', data)

            data = ""
            tmp = ""
            while len(data)<size:
                try:
                    tmp = sock.recv(size-len(data))
                except socket.timeout:
                    continue

                # unfortunately, we have to do some stupid stuff here, to avoid infinite loops...
                if not tmp:
                    errorCount += 1
                    if errorCount > 3:
                        # lost connection
                        self.logger.error("Connection error #ERROR_CON006")
                        break
                    continue
                else:
                    data += tmp
        except socket.error:
            #print "Connection error #ERROR_CON015"
            sock.close()
            sock = None
            return None

        if not data or errorCount > 3:
            # lost connection
            #print "Connection error #ERROR_CON007"
            sock.close()
            sock = None
            return None

        content = struct.unpack(str(size) + 's', data)[0]

        return DataPacket(command, source, streamid, size, content)

    def connect(self, user, serverinfo):
        # empty queue
        while 1:
            try:
                self.receivedMessages.get_nowait()
            except queue.Empty:
                break

        if len(user.language)==0:
            user.language = "en_GB"
        # TODO: check the rest of the input

        # reset some variables
        self.streamID = 10
        self.uid = 0
        self.netQuality = 0
        self.serverinfo = serverinfo

        self.logger.debug("Creating socket...")
        self.runCondition = 1
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except socket.error as msg:
            self.socket = None
            self.logger.error("Couldn't create socket.")
            return False
        self.logger.info("Created socket...")

        self.logger.debug("Trying to connect to server %s:%d", self.serverinfo.host, self.serverinfo.port)
        try:
            self.socket.connect((u"%s" % self.serverinfo.host, self.serverinfo.port))
        except socket.error as msg:
            self.socket.close()
            self.socket = None
            self.logger.error("Couldn't connect to server %s:%d", self.serverinfo.host, self.serverinfo.port)
            return False
        self.logger.info("Connected to server %s:%d", self.serverinfo.host, self.serverinfo.port)

        receiveThread = threading.Thread(target=self.__start_receive_thread)
        receiveThread.setDaemon(True)
        receiveThread.start()

        # send hello
        self.logger.debug("Successfully connected! Sending hello message.")
        self.__sendHello(self.serverinfo.protocolversion)

        # receive hello
        packet = self.receiveMsg()

        if packet is None:
            self.logger.critical("Server didn't respond.")
            return False

        if packet.command != MSG2_HELLO:
            self.logger.error("Received %s while expecting MSG2_HELLO Exiting...", commandName(packet.command))
            self.disconnect()
            return False
        self.logger.debug("Received server info.")
        self.serverinfo.update(processServerInfo(packet.data))

        self.logger.debug("Sending our user info.")
        self.__sendUserInfo(user)

        # receive a welcome message with our own user data
        packet = self.receiveMsg()

        if packet is None:
            self.logger.critical("Server sent nothing, while it should have sent us a welcome message.")
            return False

        # Some error handling
        if packet.command != MSG2_WELCOME:
            if packet.command == MSG2_FULL:
                self.logger.error("This server is full :(")
            elif packet.command == MSG2_BANNED:
                self.logger.error("We're banned from this server :/")
            elif packet.command == MSG2_WRONG_PW:
                self.logger.error("Wrong password :|")
            elif packet.command == MSG2_WRONG_VER:
                self.logger.error("Wrong protocol version! O.o")
            else:
                self.logger.error("invalid handshake: MSG2_HELLO (server error?)")
            self.logger.error("Unable to connect to this server. Exiting...")
            self.disconnect()
            return False

        # process our userdata
        user.update(processUserInfo(packet.data))
        self.logger.info("joined as '%s' on slot %d with UID %s and auth %d", user.username, user.slotnum, str(user.uniqueID), user.authstatus)
        self.sm.addClient(user)
        self.uid = user.uniqueID

        # Receive the user join message
        #packet = self.receiveMsg()
        #if packet.command != MSG2_USER_JOIN:
        #       self.logger.error("Missing message USER_JOIN. Connection failed.")
        #       self.disconnect()
        #       return False

        # register character stream
        s = stream_info_t()
        s.name = b"default"
        s.type = TYPE_CHARACTER
        s.status = 0
        s.regdata = chr(2)
        print("stream default: %d" % self.registerStream(s))

        # register chat stream
        s = stream_info_t()
        s.name = b"chat"
        s.type = TYPE_CHAT
        s.status = 0
        s.regdata = 0
        print("stream chat: %d" % self.registerStream(s))

        # set the time when we connected (needed to send stream data)
        self.connectTime = time.time()

        # successfully connected
        return True

    #  pre: nothing
    # post: Disconnected from the server
    def disconnect(self):
        self.logger.info("Disconnecting...")
        self.runCondition = 0
        time.sleep(5)
        if not self.socket is None:
            self.__sendUserLeave()
            print('closing socket')
            self.socket.close()
        self.socket = None

    # Internal use only!
    def __sendUserInfo(self, user):
        data = struct.pack('Iiii40s40s40s10s10s25s40s10s128s',
                int(user.uniqueID),
                int(user.authstatus),
                int(user.slotnum),
                int(user.colournum),
                b(user.username),
                b(hashlib.sha1(b(user.usertoken)).hexdigest().upper()),
                b(hashlib.sha1(b(user.serverpassword)).hexdigest().upper()),
                b(user.language),
                b(user.clientname),
                b(user.clientversion),
                b(user.clientGUID),
                b(user.sessiontype),
                b(user.sessionoptions)
        )
        self.sendMsg(DataPacket(MSG2_USER_INFO, 0, 0, len(data), data))

    # Internal use only!
    def __sendHello(self, version):
        self.sendMsg(DataPacket(MSG2_HELLO, 0, 0, len(version), version))

    # Internal use only!
    # use disconnect() instead
    def __sendUserLeave(self):
        self.sendMsg(DataPacket(MSG2_USER_LEAVE, self.uid, 0, 0, 0))

    #  pre: A connection to the server has been established
    # post: The stream has been registered with the server and with the streammanager
    def registerStream(self, s):
        s.origin_sourceid = self.uid
        s.origin_streamid = self.streamID
        s.time = -1
        if s.type==TYPE_TRUCK:
            data = struct.pack('4i128s2i60s60s', s.type, s.status, s.origin_sourceid, s.origin_streamid, s.name, s.bufferSize, s.time, s.skin, s.sectionConfig)
        else:
            data = struct.pack('iiii128s128s', s.type, s.status, s.origin_sourceid, s.origin_streamid, s.name, b(str(s.regdata)))
        self.sendMsg(DataPacket(MSG2_STREAM_REGISTER, s.origin_sourceid, s.origin_streamid, len(data), data))
        self.sm.addStream(s)
        self.streamID += 1
        return s.origin_streamid

    #  pre: A stream has been registered
    # post: The stream is no longer registered
    def unregisterStream(self, streamID):
        data = struct.pack('i', streamID)
        self.sendMsg(DataPacket(MSG2_STREAM_UNREGISTER, self.uid, streamID, len(data), data))
        self.sm.delStream(self.uid, streamID)

    #  pre: A stream has been received
    # post: A positive/negative reply has been sent back
    def replyToStreamRegister(self, data, status):
        # TODO: Is this correct, according to the RoRnet_2.3 specifications?
        data_out = struct.pack('iiii128s128s', data.type, status, data.origin_sourceid, data.origin_streamid, data.name, b(data.regdata))
        self.sendMsg(DataPacket(MSG2_STREAM_REGISTER_RESULT, self.uid, data.origin_streamid, len(data_out), data_out))

    #  pre: A character stream has been registered
    # post: The data is sent
    def streamCharacter(self, pos, rot, animMode, animTime):
        # pack: command, posx, posy, posz, rotx, roty, rotz, rotw, animationMode[255], animationTime
        data = struct.pack('i5f10s', CHARACTER_CMD_POSITION, rot.x, rot.y, rot.z, rot.w, animTime, b(animMode))
        self.sendMsg(DataPacket(MSG2_STREAM_DATA, self.uid, self.sm.getCharSID(self.uid), len(data), data))

    #  pre: A truck stream has been registered
    # post: The data is sent
    def streamTruck(self, s, streamID, recalcTime = True):
        if recalcTime:
            theTime = math.floor((time.time()-self.connectTime)*1000)
        else:
            theTime = s.time
        data = struct.pack('=IfffIfffIfff{0}s'.format(len(s.node_data)), theTime, s.engine_speed, s.engine_force, s.engine_clutch, s.engine_gear, s.hydrodirstate, s.brake, s.wheelspeed, s.flagmask, s.refpos.x, s.refpos.y, s.refpos.z, s.node_data)
        self.sendMsg(DataPacket(MSG2_STREAM_DATA, self.uid, streamID, len(data), data))

    #  pre: A character stream has been registered
    # post: The data is sent
    def attachCharacter(self, enabled, position):
        pass

    #  pre: The chat stream has been registered (OK if the connect function is called)
    # post: A chat message is sent
    def sendChat(self, msg):
        if not self.socket:
            return False
        # cast to unicode if necessary
        # if type(msg) is str:
            # msg = unicode(msg, "utf-8")
        self.logger.debug("Sending chat: '%s'", msg)
        newMsg = msg.encode('utf-8')
        self.sendMsg(DataPacket(MSG2_UTF_CHAT, self.uid, self.sm.getChatSID(self.uid), len(newMsg), newMsg))


        return True

    def sendUserChat(self, user, msg):
        if not self.socket:
            return False

        self.logger.debug("Sending chat: '%s'", msg)
        newMsg = "BOTAPI.SAY_COMMENT$%s: %s" % (user, msg)
        newMsg = newMsg.encode('utf-8')
        self.sendMsg(DataPacket(MSG2_GAME_CMD, self.uid, 7, len(newMsg), newMsg))


        return True

    # This function will automatically split up your message is smaller chunks, so it looks nicer
    #  pre: The chat stream has been registered (OK if the connect function is called)
    # post: A chat message is sent
    def sendChat_splitted(self, msg):
        if not self.socket:
            return False

        # word wrap size
        maxsize = 100
        if len(msg) > maxsize:
            self.logger.debug("%d=len(msg)>maxsize=%d", len(msg), maxsize)
            for i in range(0, int(math.ceil(float(len(msg)) / float(maxsize)))):
                if i == 0:
                    msga = msg[maxsize*i:maxsize*(i+1)]
                    self.logger.debug("sending %s", msga)
                    self.sendMsg(DataPacket(MSG2_UTF_CHAT, self.uid, self.sm.getChatSID(self.uid), len(msga), unicode(msga, errors='ignore').encode('utf-8')))
                else:
                    msga = "| "+msg[maxsize*i:maxsize*(i+1)]
                    self.logger.debug("sending %s", msga)
                    self.sendMsg(DataPacket(MSG2_UTF_CHAT, self.uid, self.sm.getChatSID(self.uid), len(msga), unicode(msga, errors='ignore').encode('utf-8')))
        else:
            self.sendMsg(DataPacket(MSG2_UTF_CHAT, self.uid, self.sm.getChatSID(self.uid), len(msg), unicode(msg, errors='ignore').encode('utf-8')))
        self.logger.debug("msg sent: %s", msg)

        return True

    #  pre: The chat stream has been registered (OK if the connect function is called)
    #       Unique ID 'uid' exists
    # post: A message is sent to the user
    def privChat(self, uid, msg):
        if not self.socket:
            return False

        print("sending PRIVCHAT message")
        data = struct.pack("I8000s", uid, unicode(msg, errors='replace').encode('utf-8'))
        self.sendMsg(DataPacket(MSG2_UTF_PRIVCHAT, self.uid, self.sm.getChatSID(self.uid), len(data), data))

        return True

    # post: A script command is sent
    def sendGameCmd(self, msg):
        if not self.socket:
            return False

        self.sendMsg(DataPacket(MSG2_GAME_CMD, self.uid, 0, len(msg), msg))
        self.logger.debug("game command sent: %s", msg)

        return True


    #  pre: The chat stream has been registered (OK if the connect function is called)
    #       We're admin or moderator
    #       Unique ID 'uid' exists
    # post: A user is kicked
    def kick(self, uid, reason="no reason"):
        self.sendChat("!kick %d %s" % (uid, reason))

    #  pre: The chat stream has been registered (OK if the connect function is called)
    #       We're admin or moderator
    #       Unique ID 'uid' exists
    # post: A user is banned and kicked
    def ban(self, uid, reason="no reason"):
        self.sendChat("!ban %d %s" % (uid, reason))

    #  pre: The chat stream has been registered (OK if the connect function is called)
    #       We're admin or moderator
    # post: A message from "Host(general)" is sent
    def say(self, uid, reason):
        self.sendChat("!say %d %s" % (uid, reason))

    # Internal use only!
    # Use sendMsg instead
    def __sendRaw(self, data):
        if self.socket is None:
            return False

        try:
            #print data
            if data is None:
                return

            self.socket.send(data)
        except Exception as e:
            self.logger.exception('sendMsg error: '+str(e))
            self.runCondition = 0
            # import traceback
            # traceback.print_exc(file=sys.stdout)
        return True

    # Internal use only!
    def __packPacket(self, packet):
        if packet.size == 0:
            # just header
            data = struct.pack('IIII', packet.command, packet.source, packet.streamid, packet.size)
        else:
            data = struct.pack('IIII'+str(packet.size)+'s', packet.command, packet.source, packet.streamid, packet.size, b(packet.data))
        return data

    def sendMsg(self, packet):
        if self.socket is None:
            return False
        if(packet.command!=MSG2_STREAM_DATA):
            self.logger.debug("S>| %-18s %03d:%02d (%d)" % (commandName(packet.command), packet.source, packet.streamid, packet.size))
        #print "S>| %-18s %03d:%02d (%d)" % (commandName(packet.command), packet.source, packet.streamid, packet.size)
        self.__sendRaw(self.__packPacket(packet))

        return True

    def receiveMsg(self, timeout=2.5):
        try:
            return self.receivedMessages.get(True, timeout)
        except queue.Empty:
            return None

    def __start_receive_thread(self):
        # We need a socket to receive...
        if self.socket is None:
            self.logger.error("Tried to receive on None socket (#ERROR_CON009)")
            return None

        self.socket.settimeout(5)

        while self.runCondition:
            # get the header
            data = b""
            tmp = b""
            errorCount = 0
            try:
                while len(data)<self.headersize and self.runCondition:
                    try:
                        tmp = self.socket.recv(self.headersize-len(data))
                    except socket.timeout:
                        continue

                    # unfortunately, we have to do some stupid stuff here, to avoid infinite loops...
                    if not tmp:
                        errorCount += 1;
                        if errorCount > 3:
                            # lost connection
                            self.logger.error("Connection error #ERROR_CON005")
                            self.runCondition = 0
                            break
                        continue
                    else:
                        data += tmp

                if not data or errorCount > 3:
                    # lost connection
                    self.logger.error("Connection error #ERROR_CON008")
                    self.runCondition = 0
                    break

                (command, source, streamid, size) = struct.unpack('IIII', data)
                if(source & 0x80000000):
                    source = -0x100000000 + source

                data = b""
                tmp = b""
                while len(data)<size and self.runCondition:
                    try:
                        tmp = self.socket.recv(size-len(data))
                    except socket.timeout:
                        continue

                    # unfortunately, we have to do some stupid stuff here, to avoid infinite loops...
                    if not tmp:
                        errorCount += 1;
                        if errorCount > 3:
                            # lost connection
                            self.logger.error("Connection error #ERROR_CON006")
                            self.runCondition = 0
                            break
                        continue
                    else:
                        data += tmp
            except socket.error:
                self.logger.error("Connection error #ERROR_CON015")
                self.runCondition = 0
                break

            if command != MSG2_STREAM_UNREGISTER: # No data
                if not data or errorCount > 3:
                    # lost connection
                    self.logger.error("Connection error #ERROR_CON007")
                    self.runCondition = 0
                    break

            content = struct.unpack(str(size) + 's', data)[0]

            if not command in [MSG2_STREAM_DATA, MSG2_UTF_CHAT, MSG2_NETQUALITY]:
                self.logger.debug("R<| %-18s %03d:%02d (%d)" % (commandName(command), source, streamid, size))

            self.receivedMessages.put(DataPacket(command, source, streamid, size, content))
        self.logger.warning("Receive thread exiting...")

    def setNetQuality(self, quality):
        if self.netQuality != quality:
            self.netQuality = quality
            return True
        else:
            return False

    def getNetQuality(self, quality):
        return self.netQuality



class Client(threading.Thread):
    lastStreamSent = 0

    #####################
    #  INITIALIZATION   #
    #####################

    def __init__(self, ID, main):
        self.logger = logging.getLogger(ID)
        self.logger.debug("logger started")

        self.ID = ID # our ID to get settings
        self.streams = {}
        self.main = main
        self.sm = streamManager()
        self.server = RoR_Connection(self.logger, self.sm)
        self.discord = Discord_Layer(self.sm, main, ID)
        self.eh = eventHandler(self.sm, self.logger, self.discord, self.server, self.main.settings, self.ID)
        self.fullShutdown = 0

        self.intsize = struct.calcsize('i')

        threading.Thread.__init__(self)

        self.logger.debug("RoRclient %s initialized", ID)

    def run(self):
        reconnectionInterval = self.main.settings.getSetting('RoRclients', self.ID, 'reconnection_interval')
        reconnectionTriesLeft = self.main.settings.getSetting('RoRclients', self.ID, 'reconnection_tries')
        timeUntilRetry = 0

        while not self.fullShutdown:
            # Start the big loop
            # This shouldn't return, unless we lose connection
            self.bigLoop()

            # disconnect if we're still connected
            if self.server.isConnected():
                self.logger.debug("Disconnecting as we're trying to connect while still connected.")
                self.server.disconnect()

            # decrement our connection tries variable
            reconnectionTriesLeft -= 1

            # Wait some seconds before trying to reconnect
            if not self.fullShutdown and reconnectionTriesLeft > 0:
                timeUntilRetry = time.time()+reconnectionInterval
                while time.time() < timeUntilRetry:
                    try:
                        data = self.main.RoRqueue[self.ID].get(True, timeUntilRetry-time.time()+1)
                    except queue.Empty:
                        pass
                    else:
                        if data[0] == "disconnect":
                            self.discord.sayInfo("Disconnecting on demand.")
                            self.fullShutdown = 1
                            break
            else:
                break

        if reconnectionTriesLeft == 0:
            self.discord.sayError("Unable to reconnect. Exiting RoRclient %s ..." % self.ID)
        elif self.fullShutdown:
            self.discord.sayInfo("RoRclient %s exiting on demand..." % self.ID)
        else:
            self.discord.sayError("RoRclient %s exiting after an unknown error occurred..." % self.ID)


    def bigLoop(self):
        # some default values
        user                = user_info_t()
        user.username       = self.main.settings.getSetting('RoRclients', self.ID, 'username')
        user.usertoken      = self.main.settings.getSetting('RoRclients', self.ID, 'usertoken')
        user.serverpassword = self.main.settings.getSetting('RoRclients', self.ID, 'password')
        user.language       = self.main.settings.getSetting('RoRclients', self.ID, 'userlanguage')
        user.clientname     = self.main.settings.getSetting('general', 'clientname')
        user.clientversion  = self.main.settings.getSetting('general', 'version_num')

        serverinfo           = server_info_t()
        serverinfo.host      = self.main.settings.getSetting('RoRclients', self.ID, 'host')
        serverinfo.port      = self.main.settings.getSetting('RoRclients', self.ID, 'port')
        serverinfo.password  = self.main.settings.getSetting('RoRclients', self.ID, 'password')
        serverinfo.pasworded = len(serverinfo.password)!=0

        # try to connect to the server
        self.logger.debug("Connecting to server")
        if not self.server.connect(user, serverinfo):
            self.discord.sayError("Couldn't connect to server (#ERROR_CON001)")
            self.logger.error("Couldn't connect to server (#ERROR_CON001)")
            return

        # double check that we're connected
        if not self.server.isConnected():
            self.discord.sayError("Couldn't connect to server (#ERROR_CON002)")
            self.logger.error("Couldn't connect to server (#ERROR_CON002)")
            return

        self.discord.sayInfo("Connected to server %s" % s(serverinfo.servername))
        print("Connected to server '%s'" % s(serverinfo.servername))

        self.connectTime = time.time()
        lastFrameTime = time.time()

        self.eh.on_connect()

        # finaly, we start this loop
        while self.server.runCondition:
            if not self.server.isConnected():
                self.logger.error("Connection to server lost")
                self.discord.sayError("Lost connection to server (#ERROR_CON003)")
                break

            packet = self.server.receiveMsg(0.03)

            # if not packet is None:
            if not packet is None:
                self.processPacket(packet)

            self.checkQueue()

            currentTime = time.time()
            if currentTime-lastFrameTime > 0.02:
                # 20 FPS, should be enough to drive a truck fluently
                self.eh.frameStep(currentTime-lastFrameTime)
                lastFrameTime = currentTime

        # We're not in the loop anymore...
        self.eh.on_disconnect()
        self.sm.clear()

    #####################
    # GENERAL FUNCTIONS #
    #####################

    def processPacket(self, packet):
        if packet.command == MSG2_STREAM_DATA:
            # Critical performance impact!
            # uncomment the following line to reduce server load:
            #return
            stream = self.sm.getStreamData(packet.source, packet.streamid)

            if(stream.type == TYPE_CHARACTER):
                streamData = processCharacterData(packet.data)
                if streamData.command == CHARACTER_CMD_POSITION:
                    self.sm.setPosition(packet.source, packet.streamid, streamData.rot)
                    self.sm.setCurrentStream(packet.source, packet.source, packet.streamid)
                elif streamData.command == CHARACTER_CMD_ATTACH:
                    self.sm.setCurrentStream(packet.source, streamData.source_id, streamData.stream_id)
                self.eh.on_stream_data(packet.source, stream, streamData)

            elif(stream.type==TYPE_TRUCK):
                if len(packet.data) >= 48:
                    streamData = processTruckData(packet.data)
                    self.sm.setPosition(packet.source, packet.streamid, streamData.refpos)
                    self.eh.on_stream_data(packet.source, stream, streamData)

            elif stream == None:
                self.logger.warning("EEE stream %-4s:%-2s not found!" % (packet.source, packet.streamid))

        elif packet.command == MSG2_NETQUALITY:
            quality = processNetQuality(packet.data)
            if self.server.setNetQuality(quality):
                self.eh.on_net_quality_change(packet.source, quality)
            #self.discord.sayDebug("quality: %d" % quality)

        elif packet.command == MSG2_UTF_CHAT:
            if packet.source > 100000:
                packet.source = -1
            str_tmp = b(packet.data).decode('utf-8').strip('\0')

            self.logger.debug("CHAT| " + str_tmp)

            self.discord.sayChat(str_tmp, packet.source)

            # ignore chat from ourself
            if (len(str_tmp) > 0) and (packet.source != self.server.uid):
                self.eh.on_chat(packet.source, str_tmp)

        elif packet.command == MSG2_STREAM_REGISTER:
            data = processRegisterStreamData(packet.data)
            self.sm.addStream(data)
            res = self.eh.on_stream_register(packet.source, data)

            if data.type == TYPE_TRUCK:
                if res != 1:
                    res = -1
                # send stream register result back
                self.server.replyToStreamRegister(data, res)

        elif packet.command == MSG2_USER_JOIN:
            # self.interpretUserInfo(packet)
            data = processUserInfo(packet.data)
            self.sm.addClient(data)
            self.discord.sayJoin(packet.source)
            if packet.source!=self.server.uid:
                self.eh.on_join(packet.source, data)

        elif packet.command == MSG2_USER_INFO:
            # self.interpretUserInfo(packet)
            data = processUserInfo(packet.data)
            self.sm.addClient(data)
            if packet.source!=self.server.uid:
                self.eh.on_join(packet.source, data)

        elif packet.command == MSG2_STREAM_REGISTER_RESULT:
            # self.interpretStreamRegisterResult(packet)
            self.eh.on_stream_register_result(packet.source, processRegisterStreamData(packet.data))

        elif packet.command == MSG2_USER_LEAVE:
            self.discord.sayLeave(packet.source)
            self.eh.on_leave(packet.source)
            if packet.source == self.server.uid:
                # it is us that left...
                # Not good!
                self.logger.error("Server closed connection (#ERROR_CON010)")
                self.server.runCondition = 0
            self.sm.delClient(packet.source)

        elif packet.command == MSG2_GAME_CMD:
            str_tmp = b(packet.data).decode('utf-8').strip('\0')
            #self.logger.debug("GAME_CMD| " + str_tmp)

            #self.discord.sayInfo('(game_cmd) '+str_tmp)

            # ignore chat from ourself
            if (len(str_tmp) > 0) and (packet.source != self.server.uid):
                self.eh.on_game_cmd((int(packet.source) | 0x80000000), str_tmp)

        elif packet.command == MSG2_UTF_PRIVCHAT:
            str_tmp = str(packet.data).decode('utf-8').strip('\0')
            self.logger.debug("CHAT| (private) " + str_tmp)

            self.discord.sayPrivChat(str_tmp, packet.source)

            # ignore chat from ourself
            if (len(str_tmp) > 0) and (packet.source != self.server.uid):
                self.eh.on_private_chat(packet.source, str_tmp)
                # self.processCommand(str_tmp, packet)

        elif packet.command == MSG2_STREAM_UNREGISTER:
            str_tmp = str(packet.data).strip('\0')

        else:
            str_tmp = str(packet.data).strip('\0')
            self.discord.sayError('Unhandled message (type: %d, from: %d): %s' % (packet.command, packet.source, str_tmp))

    def checkQueue(self):
        while not self.main.RoRqueue[self.ID].empty():
            try:
                data = self.main.RoRqueue[self.ID].get_nowait()
            except queue.Empty:
                break
            else:
                if data[0] == "disconnect":
                    self.server.sendChat("%sServices is shutting down/restarting... Be nice while I'm gone! :)" % (COLOUR_CYAN))
                    time.sleep(0.5)
                    self.discord.sayInfo("Disconnecting on demand.")
                    self.discord.sayLeave(self.server.uid)
                    self.server.disconnect()
                    self.fullShutdown = 1
                    return
                elif data[0] == "msg":
                    self.server.sendChat(data[1])
                elif data[0] == "cmd":
                    self.server.sendGameCmd(data[1])
                elif data[0] == "msg_with_source":
                    self.server.sendChat("%s[%s%s%s@Discord%s]: %s" % (COLOUR_WHITE, COLOUR_GREEN, data[2], COLOUR_RED, COLOUR_WHITE, data[1]))
                elif data[0] == "privmsg":
                    self.server.privChat(data[1], data[2])
                elif data[0] == "kick":
                    self.server.kick(data[1], data[2])
                elif data[0] == "ban":
                    self.server.ban(data[1], data[2])
                elif data[0] == "say":
                    self.server.say(data[1], data[2])
                elif data[0] == "list_players":
                    self.showPlayerList()
                elif data[0] == "player_info":
                    self.discord.playerInfo(data[1])
                elif data[0] == "global_stats":
                    self.discord.globalStats()
                elif data[0] == "info":
                    if data[1] == "full":
                        if self.server.serverinfo.passworded:
                            str_tmp = "Private"
                        else:
                            str_tmp = "Public"
                        self.discord.sayInfo("%s server '%s':" % (str_tmp, s(self.server.serverinfo.servername)))
                        self.discord.sayInfo("running on %s:%d, using %s" % (self.server.serverinfo.host, self.server.serverinfo.port, self.server.serverinfo.protocolversion))
                        self.discord.sayInfo("terrain: %s     Players: %d" % (s(self.server.serverinfo.terrain), self.sm.countClients()))
                    elif data[1] == "short":
                        self.discord.sayInfo("name: '%s' - terrain: '%s' - players: %d" % (s(self.server.serverinfo.servername), s(self.server.serverinfo.terrain), self.sm.countClients()))
                    elif data[1] == "ip":
                        self.discord.sayInfo("name: '%s' - host: %s:%d" % (s(self.server.serverinfo.servername), self.server.serverinfo.host, self.server.serverinfo.port))
                elif data[0] == "stats":
                    pass
                else:
                    # Unknown command... maybe some user edit?
                    self.eh.on_discord(data)

    def showPlayerList(self):
        # get list of online UIDs
        keys = self.sm.getOnlineUserIdentifiers()
        keys.sort()

        # Get length of longest username
        usernamefieldlen = 5
        authfieldlen = 0
        uidfieldlen = 3
        for uid in keys:
            if uid<=0:
                continue
            if len(self.sm.getUsername(uid))>usernamefieldlen:
                usernamefieldlen = len(self.sm.getUsername(uid))
            if len(rawAuthToString(self.sm.getAuth(uid)))>authfieldlen:
                authfieldlen = len(rawAuthToString(self.sm.getAuth(uid)))
            if len(str(uid))>uidfieldlen:
                uidfieldlen = len(str(uid))

        # print header
        self.discord.sayInfo("%s | %3s | %5s | %s" % ("Username", "UID", "Lang", "Current vehicle"))

        # Print the actual list
        noPlayers = True
        slotnum = 0
        for uid in keys:
            if(uid>0):

                currentVehicle = self.sm.getCurrentStream(uid).name
                if uid==self.server.uid:
                    currentVehicle = "N/A"
                elif currentVehicle == "default":
                    currentVehicle = "N/A"
                elif currentVehicle == "":
                    currentVehicle = "unknown"
                else:
                    info = getTruckInfo(currentVehicle)
                    currentVehicle = "%s (%s)" % (s(info['name']), s(info['type']))

                self.discord.sayInfo("%2d %s %s | %s | %5s | %s" % (slotnum, rawAuthToString(self.sm.getAuth(uid)), self.sm.getUsername(uid), str(uid), s(self.sm.getLanguage(uid).replace(b'_', b' ')), currentVehicle))
                noPlayers = False

                slotnum += 1

        if noPlayers:
            self.discord.sayInfo("There are no players online.")


#####################
#   EVENT HANDLING  #
#####################
# Just to split optional things from important things
# You can clear out (BUT NOT REMOVE) all functions here, without problems
# The following functions will be called by the Client class:
# on_connect, on_join, on_leave, on_chat, on_private_chat, on_stream_register,
# on_stream_register_result, on_game_cmd, on_disconnect, frameStep, on_irc
class eventHandler:
    time_ms, time_sec, fps, lastFps, countDown = (0.0, 0, 0, 0, -1)

    def __init__(self, streamManager, logger, discord, server, settings, ID):
        self.sm       = streamManager
        self.logger   = logger
        self.discord  = discord
        self.server   = server
        self.settings = settings
        self.serverID = ID
        self.chatDelayed = []
        self.sr       = streamRecorder(server)
        self.charAnim = CHAR_IDLE_SWAY

    def on_connect(self):
        self.connectTime = time.time()

    def on_join(self, source, user):
        #if "fuck" in user.username.lower():
        #       self.server.sendChat("!say %d This is an official warning. Please mind your language!" % source)
        #       self.server.kick(source, "having a forbidden username.")
        #self.server.sendGameCmd("CIFPO_CLIENTVERSION$%d$%s" % (source, user.clientversion))
        pass

    def on_leave(self, source):
        pass

    def on_chat(self, source, message):
        a = message.split(" ", 1)
        if len(a)>1:
            args = a[1].split(" ", 5)
        else:
            args = []

        if source == -1:
            return

        #if "http" in message.lower():
            # Simple anti-link protection
        #       self.server.kick(source, "Links are prohibited [auto-kick]")
        #       return

        if len(a[0])==0:
            return

        if a[0][0] != "-":
            return

        if a[0] == "-say":
            # if len(a)>1:
                # self.server.sendChat(a[1])
            # else:
                # self.server.sendChat("Syntax: -say <message>")
            self.__sendChat_delayed("This command has been disabled because it's quite useless. Use the !say command instead.")

        elif a[0] == "-ping":
            self.__sendChat_delayed("pong! :) (this bot doesn't provide latency statistics. Try using !ping instead.)")

        elif a[0] == "-pong":
            self.__sendChat_delayed("... what are you doing? That's my text! You're supposed to say -ping, so I can say pong. Not the other way around!!!")

        elif a[0] == "-countdown":
            # Initialize a countdown
            self.__sendChat_delayed("Countdown started by %s" % self.sm.getUsernameColoured(source))
            self.countDown = 3

        elif a[0] == "-countdown2":
            # Initialize a countdown
            self.__sendChat_delayed("Countdown started by %s" % self.sm.getUsernameColoured(source))
            self.countDown = 5

        elif a[0] == "-brb":
            self.__sendChat_delayed("%s will be right back!" % self.sm.getUsernameColoured(source))

        elif a[0] == "-afk":
            self.__sendChat_delayed("%s is now away from keyboard! :(" % self.sm.getUsernameColoured(source))

        elif a[0] == "-back":
            self.__sendChat_delayed("%s is now back! :D" % self.sm.getUsernameColoured(source))

        elif a[0] == "-gtg":
            self.__sendChat_delayed("%s got to go! :( Say bye!" % self.sm.getUsernameColoured(source))

        elif a[0] == "-version":
            self.__sendChat_delayed("version: %s" % self.settings.getSetting('general', 'version_str'))

        elif a[0] == "-kickme":
            # this can be abused. ("How do I do this or that" -> "Say -kickme to do that")
            self.server.kick(source, "He asked for it... literally!")

        # Roleplay commands

        elif a[0] == "-give":
            self.__sendChat_delayed("This command has been disabled because it's quite useless.")

        elif a[0] == "-r":
            self.__sendChat_delayed("This command has been disabled because it's quite useless.")

        elif a[0] == "-police":
            if len(a)>1:
                self.__sendChat_delayed("%s is requesting law enforcement at %s" % (self.sm.getUsernameColoured(source), a[1]))
            else:
                self.__sendChat_delayed("Usage: -police location")

        elif a[0] == "-ems":
            if len(a)>1:
                self.__sendChat_delayed("%s is requesting emergency medical services at %s" % (self.sm.getUsernameColoured(source), a[1]))
            else:
                self.__sendChat_delayed("Usage: -ems location")

        elif a[0] == "-fire":
            if len(a)>1:
                self.__sendChat_delayed("%s is requesting the fire department at %s" % (self.sm.getUsernameColoured(source), a[1]))
            else:
                self.__sendChat_delayed("Usage: -fire location")

        elif a[0] == "-rip":
            if len(a)>1:
                self.__sendChat_delayed("RiP %s%s%s you have been our greatest source of inspiration and courage!" % (COLOUR_CYAN, a[1], COLOUR_WHITE))
            else:
                self.__sendChat_delayed("Usage: -rip name")

        # End roleplay commands

        elif a[0] == "-help":
            self.__sendChat_delayed("Available commands: -version, -countdown, -countdown2, -brb, -afk, -back, -gtg, -police, -ems, -fire, -rip, -kickme, -getpos, !version, !rules, !motd, !vehiclelimit, !boost, !boost2, !boost3, !boost4")

        elif a[0] == "-rules":
            self.__sendChat_delayed("Wrong prefix. Correct form is: !rules")

        elif a[0] == "-motd":
            self.__sendChat_delayed("Wrong prefix. Correct form is: !motd")

        elif a[0] == "-vehiclelimit":
            self.__sendChat_delayed("Wrong prefix. Correct form is: !vehiclelimit")

        elif a[0] == "-boost":
            self.__sendChat_delayed("Wrong prefix. Correct form is: !boost")

        elif a[0] == "-boost2":
            self.__sendChat_delayed("Wrong prefix. Correct form is: !boost2")

        elif a[0] == "-boost3":
            self.__sendChat_delayed("Wrong prefix. Correct form is: !boost3")

        elif a[0] == "-boost4":
            self.__sendChat_delayed("Wrong prefix. Correct form is: !boost4")

        elif a[0] == "-record":
            if not self.sm.getAuth(source) & ( AUTH_ADMIN | AUTH_MOD ):
                self.__sendChat_delayed("You don't have permission to use this command!")
            elif len(args)<1:
                self.__sendChat_delayed("Usage: -record <start|stop|pause|continue>")
                pass
            elif args[0] == "start":
                if len(args) > 1:
                    self.__sendChat_delayed(
                            self.sr.startRecording(
                                    self.sm.getUserData(source),
                                    self.sm.getStreamData(self.sm.getCurrentStream(source).origin_sourceid,
                                    self.sm.getCurrentStream(source).origin_streamid),
                                    args[1]
                            )
                    )
                else:
                    self.__sendChat_delayed(
                            self.sr.startRecording(
                                    self.sm.getUserData(source),
                                    self.sm.getStreamData(self.sm.getCurrentStream(source).origin_sourceid,
                                    self.sm.getCurrentStream(source).origin_streamid)
                            )
                    )
            elif args[0] == "stop":
                self.__sendChat_delayed("Filename: %s" % self.sr.stopRecording(source))
            elif args[0] == "pause":
                self.sr.pauseRecording(source)
                self.__sendChat_delayed("Paused.")
            elif args[0] == "continue" or args[0] == "unpause":
                self.sr.unpauseRecording(source)
                self.__sendChat_delayed("Recording...")

        elif a[0] == "-playback":
            if not self.sm.getAuth(source) & ( AUTH_ADMIN | AUTH_MOD ):
                self.__sendChat_delayed("You don't have permission to use this command!")
            else:
                if len(args)<1:
                    self.__sendChat_delayed("Usage: -playback <start|stop|pause|continue>")
                    pass
                elif args[0] == "start":
                    if len(args) > 1:
                        self.__sendChat_delayed("Playing... ID = %d" % self.sr.startPlayback(args[1]))
                    else:
                        self.__sendChat_delayed("Playing... ID = %d" % self.sr.startPlayback('last'))
                elif args[0] == "stop":
                    self.sr.stopPlayback()
                    self.__sendChat_delayed("Stopped.")
                elif args[0] == "pause":
                    self.sr.pausePlayback()
                    self.__sendChat_delayed("Paused.")
                elif args[0] == "continue" or args[0] == "unpause":
                    self.sr.unpausePlayback()
                    self.__sendChat_delayed("Playing...")

        elif a[0] == "-getpos":
            if len(a)<=1:
                pos = self.sm.getPosition(source)
                self.__sendChat_delayed("%s your position is: (x: %f, y: %f, z: %f)" % (COLOUR_CYAN, pos.x, pos.y, pos.z))
            else:
                try:
                    a[1] = int(a[1])
                except ValueError:
                    self.__sendChat_delayed("Usage: -getpos <streamID>")
                else:
                    pos = self.sm.getPosition(source, a[1])
                    self.__sendChat_delayed("%s, position of %d is: (%f, %f, %f)" % (self.sm.getUsernameColoured(source), a[1], pos.x, pos.y, pos.z))

        #elif a[0] == "-test":
        #       if isPointIn2DSquare(vector3(5,5,0), (vector3(0,0,0), vector3(0,10,0), vector3(10,10,0), vector3(10,0,0))):
        #               self.__sendChat_delayed("OK")
        #       else:
        #               self.__sendChat_delayed("not OK")
        #
        #       if isPointIn2DSquare(vector3(20,20,0), (vector3(0,0,0), vector3(0,10,0), vector3(10,10,0), vector3(10,0,0))):
        #               self.__sendChat_delayed("not OK")
        #       else:
        #               self.__sendChat_delayed("OK")

        elif a[0] == "-fps":
            self.__sendChat_delayed("current FPS of Services: %d" % self.lastFps)

        else:
            pass

    # This function queues messages, and send them a few milliseconds later.
    # This avoids that players see the answer before the command.
    def __sendChat_delayed(self, msg):
        self.chatDelayed.append((time.time(), msg))

    def process_chatDelayed(self):
        currentTime = time.time()
        while len(self.chatDelayed)>0:
            msg = self.chatDelayed[0]
            if(currentTime-msg[0]<0.2):
                break
            else:
                self.server.sendChat(self.chatDelayed.pop()[1])

    def on_private_chat(self, source, message):
        pass

    def on_stream_register(self, source, stream):
        if(stream.type==TYPE_TRUCK):
            if time.time()-self.connectTime > 10: # wait 10 seconds, as we don't want to spam the chat on join
                self.discord.sayStreamReg(source,stream)
        return -1

    def on_stream_register_result(self, source, stream):
        pass

    def on_game_cmd(self, source, cmd):
        # print cmd
        prog = re.compile(r'game\.message\(["\']([^"\n]+)["\'], ["\']([a-zA-Z0-9:\._]+)["\'], ([0-9\.f]+), ([a-z]+)\)', flags=(re.MULTILINE | re.DOTALL))
        result = prog.findall(cmd)

        for i in range(0,len(result)):
            if result[i][1]=="user_comment.png":
                # this is a fake chat message
                # User to uid
                prog2 = re.compile(r'#[0-9A-Fa-f]{6}([^#]+)#[0-9A-Fa-f]{6}: (.+)')
                res2 = prog2.match(result[i][0])
                if res2 is None:
                    self.discord.sayChat(result[i][0], source)
                else:
                    uid = self.sm.getUIDByName(res2.group(1))
                    self.discord.sayChat(res2.group(2), uid)
            else:
                self.discord.sayChat(result[i][0], source)
        if len(result)==0 and 'game.message' in cmd:
            self.discord.sayDebug(cmd.replace('\n', 'EOL'))
        #game.message("#FFCC00Anonymous#000000: Im coming", "user_comment.png", 30000.0f, true)

        self.logger.debug(cmd)

        pass

    def on_disconnect(self):
        pass

    def frameStep(self, dt):
        self.time_ms += dt
        self.fps += 1

        self.process_chatDelayed()

        self.sr.frameStep()

        if self.fps%3==0:
            if self.serverID == "nhelens":
                self.server.streamCharacter(
                        vector3(0, 0, 0),      # (posx, posy, posz)
                        vector4(715.261, 45.511, 2415.434, 0), # (rotx, roty, rotz, rotw)
                        CHAR_IDLE_SWAY,                               # animationMode[255]
                        0.3                                   # animationTime
                )

            elif self.serverID == "wildwest":
                self.server.streamCharacter(
                        vector3(0, 0, 0),      # (posx, posy, posz)
                        vector4(1877.213, 114.170, 2180.039, 0), # (rotx, roty, rotz, rotw)
                        CHAR_IDLE_SWAY,                               # animationMode[255]
                        0.3                                   # animationTime
                )

            else: # neo
                self.server.streamCharacter(
                        vector3(0, 0, 0),      # (posx, posy, posz)
                        vector4(2432.702, 507.300, 1713.555, 0), # (rotx, roty, rotz, rotw)
                        CHAR_IDLE_SWAY,                               # animationMode[255]
                        0.3                                   # animationTime
                )

        if self.time_ms > 1.0:
            self.time_ms -= 1.0
            self.time_sec += 1
            self.lastFps = self.fps
            self.fps     = 0

            if self.charAnim==CHAR_IDLE_SWAY:
                self.charAnim = CHAR_SPOT_SWIM
            elif self.charAnim==CHAR_SPOT_SWIM:
                self.charAnim = CHAR_WALK
            elif self.charAnim==CHAR_WALK:
                self.charAnim = CHAR_TURN
            elif self.charAnim==CHAR_TURN:
                self.charAnim = CHAR_SPOT_SWIM
            else:
                self.charAnim = CHAR_IDLE_SWAY

            # countdown system
            if self.countDown > 0:
                self.server.sendChat("%s          %d" % (COLOUR_CYAN, self.countDown))
                self.countDown -= 1
            elif self.countDown == 0:
                self.server.sendChat("%s          0    !!! GO !!! GO !!! GO !!! GO !!!" % COLOUR_CYAN)
                self.countDown -= 1

            # anouncement system
            if self.settings.getSetting('RoRclients', self.serverID, 'announcementsEnabled') and self.time_sec % self.settings.getSetting('RoRclients', self.serverID, 'announcementsDelay') == 0:
                self.server.sendChat("#FFFF00ANNOUNCEMENT: %s" % self.settings.getSetting('RoRclients', self.serverID, 'announcementList', (self.time_sec/self.settings.getSetting('RoRclients', self.serverID, 'announcementsDelay'))%len(self.settings.getSetting('RoRclients', self.serverID, 'announcementList'))))


            # To keep our socket open, we just stream some character data every second
            # We let it stand somewhere on the map, not moving at all...
            if False:
                # RoRnet_2.35 and later
                #nhelens
                if self.time_sec%3==0:
                    self.server.streamCharacter(
                            vector3(2540.9, 100.958, 2140.68),      # (posx, posy, posz)
                            vector4(0.000000, 0, 0.000000, 0), # (rotx, roty, rotz, rotw)
                            CHAR_SPOT_SWIM,                               # animationMode[255]
                            0.0                                   # animationTime
                    )
                elif self.time_sec%3==1:
                    self.server.streamCharacter(
                                    vector3(2540.9, 100.958, 2140.68),      # (posx, posy, posz)
                                    vector4(0.000000, 0, 0.000000, 0.0), # (rotx, roty, rotz, rotw)
                                    CHAR_SWIM_LOOP,                               # animationMode[255]
                                    0.0                                   # animationTime
                    )

                elif self.time_sec%3==2:
                    self.server.streamCharacter(
                                    vector3(2540.9, 100.958, 2140.68),      # (posx, posy, posz)
                                    vector4(0.000000, 0, 0.000000, 0), # (rotx, roty, rotz, rotw)
                                    CHAR_TURN,                               # animationMode[255]
                                    0.0                                   # animationTime
                    )
                elif self.time_sec%3==3:
                    self.server.streamCharacter(
                                    vector3(2540.9, 100.958, 2140.68),      # (posx, posy, posz)
                                    vector4(0.000000, 358.763, 0.000000, 0), # (rotx, roty, rotz, rotw)
                                    CHAR_TURN,                               # animationMode[255]
                                    0.0                                   # animationTime
                    )



                #penguinville
                # self.server.streamCharacter(
                    # vector3(430.758, 3.37, 473.427),      # (posx, posy, posz)
                    # vector4(0.000000, 0.0, 0.000000, 0.00), # (rotx, roty, rotz, rotw)
                    # "Idle_sway",                               # animationMode[255]
                    # random.random()                                   # animationTime
                # )

    def on_discord(self, data):
        if data[0] == "fps":
            self.discord.sayInfo("Current bot fps: %d" % self.lastFps)
        else:
            print("UNKONWN DISCORD COMMAND")
            print(data)

    def on_stream_data(self, source, stream, data):
        self.sr.addToRecording(stream, data)

    def on_net_quality_change(self, source, quality):
        if quality==1:
            self.discord.sayWarning("Connection problem detected.")
        elif quality==0:
            self.discord.sayWarning("Connection problem resolved.")


class races:
    def __init__(self, streamManager, logger, discord, server, settings, ID):
        self.sm       = streamManager
        self.logger   = logger
        self.discord  = discord
        self.server   = server
        self.settings = settings
        self.serverID = ID

        self.participants = {}

    def on_stream_data(self, source, data):
        pass

    def startRace(self, racename):
        pass


class streamRecorder:

    def __init__(self, serverInstance):
        self.recordings = {}
        self.lastFile = ''
        self.playList = []
        self.server = serverInstance
        self.version = "streamRecorder v0.01a - Report bugs to neorej16"

    def startRecording(self, user, stream, filename = "[default]", active = True):
        # We can't record everything
        if stream.origin_sourceid != user.uniqueID:
            return "You can only record your own streams..."
        if stream.type == TYPE_CHARACTER:
            return "Recording characters isn't possible yet."

        # initialize everything for recording
        if not user.uniqueID in self.recordings:
            self.recordings[user.uniqueID] = {}
        self.recordings[stream.origin_sourceid][stream.origin_streamid] = {
                'filename': filename,
                'active': active,
                'playInfo': {
                        'position': 1,
                        'lastPosition': 0,
                        'playing': 0,
                        'streamID': 0,
                        'protocol': RORNET_VERSION,
                        'version': self.version,
                        'lastFrame': 0,
                },
                'user': user,
                'stream': stream,
                'data': []
        }
        return "Recording... (%d:%d)" % (stream.origin_sourceid, stream.origin_streamid)

    def stopRecording(self, uid, streamID = -1, save = True):
        filename = "ERROR_RECORDING-NOTFOUND"
        if uid in self.recordings:
            if streamID == -1:
                for sid in self.recordings[uid]:
                    self.recordings[uid][sid]['active'] = False
                    filename = self.saveRecording(self.recordings[uid][sid])
                del self.recordings[uid]
            elif streamID in self.recordings[uid]:
                self.recordings[uid][streamID]['active'] = False
                filename = self.saveRecording(self.recordings[uid][streamID])
                del self.recordings[uid][streamID]
                if len(self.recordings[uid]) == 0:
                    del self.recordings[uid]
        self.lastFile = filename
        return filename

    def pauseRecording(self, uid, streamID = -1, save = False):
        if uid in self.recordings:
            if streamID == -1:
                for sid in self.recordings[uid]:
                    self.recordings[uid][sid]['active'] = False
            elif streamID in self.recordings[uid]:
                self.recordings[uid][streamID]['active'] = False

    def unpauseRecording(self, uid, streamID = -1, save = False):
        if uid in self.recordings:
            if streamID == -1:
                for sid in self.recordings[uid]:
                    self.recordings[uid][sid]['active'] = True
            elif streamID in self.recordings[uid]:
                self.recordings[uid][streamID]['active'] = True

    def saveRecording(self, recording):
        recording['playInfo']['count'] = len(recording['data'])
        if recording['playInfo']['count'] == 0:
            return "ERROR_NO-DATA-RECORDED"
        if recording['filename'] == '[default]':
            recording['filename'] = "%d-%04d-%02d" % (time.time(), recording['user'].uniqueID, recording['stream'].origin_streamid)
        file = open("recordings/%s.rec" % recording['filename'], 'wb')
        pickle.dump(recording, file)
        file.close()
        del file
        return recording['filename']

    def loadRecording(self, filename):
        try:
            file = open("recordings/%s.rec" % filename, 'rb')
            if file:
                recording = pickle.load(file)
                file.close()
                del file
                return recording
            else:
                return 0
        except IOError:
            return 0

    def startPlayback(self, filename, loop = True, AI = False, reUse = -1):
        if filename == 'last':
            filename = self.lastFile
        if filename == '':
            return -1
        recording = self.loadRecording(filename)
        if not recording:
            return -2
        if recording['playInfo']['protocol'] != RORNET_VERSION:
            return -3
        if recording['playInfo']['version'] != self.version:
            return -4
        recording['playInfo']['playing'] = 1
        streamID = self.server.registerStream(recording['stream'])
        recording['playInfo']['streamID'] = streamID
        recording['playInfo']['count'] = len(recording['data'])
        recording['playInfo']['lastFrame'] = time.time()
        recording['playInfo']['lastPosition'] = 0
        recording['playInfo']['position'] = 1
        self.playList.append(recording)
        return streamID

    def pausePlayback(self, streamID = -1):
        for rec in self.playList:
            if rec['playInfo']['streamID'] == streamID or streamID == -1:
                rec['playInfo']['playing'] = 0

    def unpausePlayback(self, streamID = -1):
        for rec in self.playList:
            if rec['playInfo']['streamID'] == streamID or streamID == -1:
                rec['playInfo']['playing'] = 1

    def stopPlayback(self, streamID = -1):
        self.pausePlayback(streamID)
        for rec in self.playList:
            if rec['playInfo']['streamID'] == streamID or streamID == -1:
                self.server.unregisterStream(rec['playInfo']['streamID'])
                rec['playInfo']['playing'] = 0
                del rec

    def updateStream(self, stream):
        if self.isInRecording(stream.origin_sourceid, stream.origin_streamid):
            self.recordings[stream.origin_sourceid][stream.origin_streamid]['stream'] = stream

    def isInRecording(self, uid, streamID):
        return (uid in self.recordings) and (streamID in self.recordings[uid]) and self.recordings[uid][streamID]['active']

    def addToRecording(self, stream, streamData):
        if self.isInRecording(stream.origin_sourceid, stream.origin_streamid):
            self.recordings[stream.origin_sourceid][stream.origin_streamid]['data'].append(streamData)

    def frameStep(self):
        for rec in self.playList:
            if rec['playInfo']['playing']:

                if (time.time()-rec['playInfo']['lastFrame'])*1000 > rec['data'][rec['playInfo']['position']].time-rec['data'][rec['playInfo']['lastPosition']].time-10:
                    # stream the frame
                    self.server.streamTruck(rec['data'][rec['playInfo']['position']], rec['playInfo']['streamID'])

                    # advance 1 frame in time
                    rec['playInfo']['lastFrame'] += float(rec['data'][rec['playInfo']['position']].time - rec['data'][rec['playInfo']['lastPosition']].time)/1000

                    # advance 1 frame in index
                    rec['playInfo']['lastPosition'] = rec['playInfo']['position']
                    rec['playInfo']['position'] += 1
                    if ( rec['playInfo']['position'] > (rec['playInfo']['count']-1) ):
                        rec['playInfo']['position'] = 1
                        rec['playInfo']['lastPosition'] = 0

if __name__ == '__main__':
    print("Don't start this directly! Start services_start.py")
