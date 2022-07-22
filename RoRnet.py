import struct, logging, time

RORNET_VERSION = "RoRnet_2.43"

MSG2_HELLO                      = 1025                #!< client sends its version as first message
# hello responses
MSG2_FULL                       = 1026                #!< no more slots for us
MSG2_WRONG_PW                   = 1027                #!< server send that on wrong pw
MSG2_WRONG_VER                  = 1028                #!< wrong version
MSG2_BANNED                     = 1029                #!< client not allowed to join
MSG2_WELCOME                    = 1030                #!< we can proceed

# Technical
MSG2_VERSION                    = 1031                #!< server responds with its version
MSG2_SERVER_SETTINGS            = 1032                #!< server send client the terrain name: server_info_t
MSG2_USER_INFO                  = 1033                #!< user data that is sent from the server to the clients
MSG2_MASTERINFO                 = 1034                #!< master information response
MSG2_NETQUALITY                 = 1035                #!< network quality information

# Gameplay
MSG2_GAME_CMD                   = 1036                #!< Script message. Can be sent in both directions.
MSG2_USER_JOIN                  = 1037                #!< new user joined
MSG2_USER_LEAVE                 = 1038                #!< user leaves
MSG2_UTF_CHAT                   = 1039                #!< chat line in UTF8 encoding
MSG2_UTF_PRIVCHAT               = 1040                #!< private chat line in UTF8 encoding

#Stream functions
MSG2_STREAM_REGISTER            = 1041                #!< create new stream
MSG2_STREAM_REGISTER_RESULT     = 1042                #!< result of a stream creation
MSG2_STREAM_UNREGISTER          = 1043                 #!< remove stream
MSG2_STREAM_DATA                = 1044                #!< stream data
MSG2_STREAM_DATA_DISCARDABLE    = 1045                #!< stream data that is allowed to be discarded

#Character commands
CHARACTER_CMD_POSITION = 1
CHARACTER_CMD_ATTACH   = 2

#Character modes
CHAR_IDLE_SWAY = "Idle_sway"
CHAR_SPOT_SWIM = "Spot_swim"
CHAR_WALK      = "Walk"
CHAR_RUN       = "Run"
CHAR_SWIM_LOOP = "Swim_loop"
CHAR_TURN      = "Turn"
CHAR_DRIVING   = "Driving"

# authoirizations
AUTH_NONE   = 0          #!< no authentication
AUTH_ADMIN  = 1          #!< admin on the server
AUTH_RANKED = 2          #!< ranked status
AUTH_MOD    = 4          #!< moderator status
AUTH_BOT    = 8          #!< bot status
AUTH_BANNED = 16         #!< banned

# TYPES
TYPE_TRUCK     = 0
TYPE_CHARACTER = 1
TYPE_AI        = 2
TYPE_CHAT      = 3

# NETMASKS
NETMASK_HORN        = 1    #!< horn is in use
NETMASK_LIGHTS      = 2    #!< lights on
NETMASK_BRAKES      = 4    #!< brake lights on
NETMASK_REVERSE     = 8    #!< reverse light on
NETMASK_BEACONS     = 16   #!< beacons on
NETMASK_BLINK_LEFT  = 32   #!< left blinker on
NETMASK_BLINK_RIGHT = 64   #!< right blinker on
NETMASK_BLINK_WARN  = 128  #!< warn blinker on
NETMASK_CLIGHT1     = 256  #!< custom light 1 on
NETMASK_CLIGHT2     = 512  #!< custom light 2 on
NETMASK_CLIGHT3     = 1024 #!< custom light 3 on
NETMASK_CLIGHT4     = 2048 #!< custom light 4 on
NETMASK_CLIGHT5     = 4096 #!< custom light 5 on
NETMASK_CLIGHT6     = 8192 #!< custom light 6 on
NETMASK_CLIGHT7     = 16384 #!< custom light 7 on
NETMASK_CLIGHT8     = 32768 #!< custom light 8 on
NETMASK_CLIGHT9     = 65536 #!< custom light 9 on
NETMASK_CLIGHT10     = 131072 #!< custom light 10 on
NETMASK_POLICEAUDIO = 262144 #!< police siren on
NETMASK_PARTICLE    = 524288 #!< custom particles on

# helper function to return the variable name
def commandName(cmd):
    vars = globals()
    for c in vars:
        if vars[c] == cmd and len(c) > 4 and ( c[0:5] == "MSG2_"):
            return c[5:]

def processCharacterAttachData(data):
    s = charAttach_data_t()
    s.command, s.source_id, s.stream_id, s.position = struct.unpack('4i', data)
    return s

def processCharacterPosData(data):
    s = charPos_data_t()
    if len(data) == 34:
        unpacked = struct.unpack("i5f10s", data)
        s.command, s.rot.x, s.rot.y, s.rot.z, s.rot.w, s.animationTime, s.animationMode = unpacked
        s.animationMode = s.animationMode.strip(b'\0')
    return s

def processCharacterData(data):
    thecommand = struct.unpack('i', data[0:4])[0]
    if thecommand == CHARACTER_CMD_POSITION:
        return processCharacterPosData(data)
    if thecommand == CHARACTER_CMD_ATTACH:
        return processCharacterAttachData(data)
    else:
        return charPos_data_t()


def processTruckData(data):
    s = truckStream_data_t()
    if len(data) == 48:
        fmt = '=IfffIfffIfff'
    elif len(data) > 48:
        fmt = '=IfffIfffIfff{0}s'.format(len(data) - 48)

    unpacked = struct.unpack(fmt, data)
    if len(data) == 48:
        s.time, s.engine_speed, s.engine_force, s.engine_clutch, s.engine_gear, s.hydrodirstate, s.brake, s.wheelspeed, s.flagmask, s.refpos.x, s.refpos.y, s.refpos.z = unpacked
    elif len(data) > 48:
        s.time, s.engine_speed, s.engine_force, s.engine_clutch, s.engine_gear, s.hydrodirstate, s.brake, s.wheelspeed, s.flagmask, s.refpos.x, s.refpos.y, s.refpos.z, s.node_data = unpacked
    return s

def processRegisterStreamData(data):
    s = stream_info_t()
    type = struct.unpack("i", data[:4])[0]
    if type == TYPE_CHAT or type == TYPE_CHARACTER:
        unpacked = struct.unpack("iiii128s128s", data)
        s.type, s.status, s.origin_sourceid, s.origin_streamid, s.name, s.regdata = unpacked
    elif type == TYPE_TRUCK:
        unpacked = struct.unpack("4i128s2i60s60s", data)
        s.type, s.status, s.origin_sourceid, s.origin_streamid, s.name, s.bufferSize, s.time, s.skin, s.sectionConfig = unpacked
    s.name = s.name.strip(b'\0')
    s.skin = s.skin.strip(b"\0")
    s.sectionConfig = s.sectionConfig.strip(b"\0")
    return s

def processRegisterTruckData(data):
    s = stream_info_t()
    s.type, s.status, s.origin_sourceid, s.origin_streamid, s.name, s.bufferSize, s.time, s.skin, s.sectionConfig = struct.unpack('4i128s2i60s60s', data)
    s.name = s.name.strip('\0')
    s.skin = s.skin.strip("\0")
    s.sectionConfig = s.sectionConfig.strip("\0")
    return s

def processUserInfo(data):
    u = user_info_t()
    u.uniqueID, u.authstatus, u.slotnum, u.colournum, u.username, u.usertoken, u.serverpassword, u.language, u.clientname, u.clientversion, u.clientGUID, u.sessiontype, u.sessionoptions = struct.unpack('Iiii40s40s40s10s10s25s40s10s128s', data)
    u.username       = u.username.decode('utf-8', 'ignore').strip('\0')
    u.usertoken      = u.usertoken.strip(b'\0')
    u.serverpassword = u.serverpassword.strip(b'\0')
    u.language       = u.language.strip(b'\0')
    u.clientname     = u.clientname.strip(b'\0')
    u.clientversion  = u.clientversion.strip(b'\0')
    u.clientGUID     = u.clientGUID.strip(b'\0')
    u.sessiontype    = u.sessiontype.strip(b'\0')
    u.sessionoptions = u.sessionoptions.strip(b'\0')
    return u

def processServerInfo(data):
    s = server_info_t()
    s.protocolversion, s.terrain, s.servername, s.passworded, s.info = struct.unpack('20s128s128s?4096s', data)
    s.protocolversion = s.protocolversion.strip(b'\0')
    s.terrain         = s.terrain.strip(b'\0')
    s.servername      = s.servername.strip(b'\0').replace(b'%20', b' ')
    s.info            = s.info.strip(b'\0')
    return s


def processNetQuality(data):
    (quality) = struct.unpack('I', data)
    return quality

def rawAuthToString(auth):
    result = ""
    if (auth & AUTH_ADMIN)>0:
        result += 'A'
    if (auth & AUTH_MOD)>0:
        result += 'M'
    if (auth & AUTH_RANKED)>0:
        result += 'R'
    if (auth & AUTH_BOT)>0:
        result += 'B'
    if (auth & AUTH_BANNED)>0:
        result += 'X'
    return result

class vector3:
    def __init__(self, x = 0.0, y = 0.0, z = 0.0):
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)
    def __repr__(self):
        return "vector3(%f, %f, %f)" % (self.x, self.y, self.z)
class vector4:
    def __init__(self, x = 0.0, y = 0.0, z = 0.0, w = 0.0):
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)
        self.w = float(w)
    def __repr__(self):
        return "vector4(%f, %f, %f, %f)" % (self.x, self.y, self.z, self.w)

class user_info_t:
    def __init__(self):
        self.uniqueID       = 0
        self.username       = ""
        self.usertoken      = ""
        self.serverpassword = ""
        self.language       = ""
        self.clientname     = ""
        self.clientversion  = ""
        self.clientGUID     = ""
        self.sessiontype    = ""
        self.sessionoptions = ""
        self.authstatus     = 0
        self.slotnum        = -1
        self.colournum      = -1

    def update(self, u):
        t = user_info_t()
        if u.uniqueID != t.uniqueID:
            self.uniqueID = u.uniqueID

        if u.username != t.username:
            self.username = u.username

        if u.language != t.language:
            self.language = u.language

        if u.clientname != t.clientname:
            self.clientname = u.clientname

        if u.clientversion != t.clientversion:
            self.clientversion = u.clientversion

        if u.sessiontype != t.sessiontype:
            self.sessiontype = u.sessiontype

        if u.sessionoptions != t.sessionoptions:
            self.sessionoptions = u.sessionoptions

        if u.authstatus != t.authstatus:
            self.authstatus = u.authstatus

        if u.slotnum != t.slotnum:
            self.slotnum = u.slotnum

        if u.colournum != t.colournum:
            self.colournum = u.colournum
        del t

class stream_info_t:
    def __init__(self):
        self.name = b""
        self.fileExt = b""
        self.type = -1
        self.status = -1
        self.origin_sourceid = -1
        self.origin_streamid = -1
        self.bufferSize = -1
        self.regdata = b""
        self.refpos = vector3()
        self.rot = vector4()
        self.time = -1
        self.skin = b""
        self.sectionConfig = b""

class truckStream_data_t:
    def __init__(self):
        self.time = -1
        self.engine_speed = 0.0
        self.engine_force = 0.0
        self.engine_clutch = 0.0
        self.engine_gear = 0
        self.hydrodirstate = 0.0
        self.brake = 0.0
        self.wheelspeed = 0.0
        self.flagmask = 0
        self.refpos = vector3()
        self.node_data = ""

class charPos_data_t:
    def __init__(self):
        self.command       = -1
        self.rot           = vector4()
        self.animationMode = ""
        self.animationTime = 0.0

class charAttach_data_t:
    def __init__(self):
        self.command   = -1
        self.enabled   = False
        self.source_id = -1
        self.stream_id = -1
        self.position  = -1

class user_stats_t:
    def __init__(self):
        self.onlineSince       = time.time()
        self.currentStream   = {'uniqueID': -1, 'streamID': -1}
        self.characterStreamID = -1
        self.chatStreamID      = -1
        self.distanceDriven    = 0.0
        self.distanceSailed    = 0.0
        self.distanceWalked    = 0.0
        self.distanceFlown     = 0.0

class server_info_t:
    def __init__(self):
        self.host            = ""
        self.port            = 12000
        self.protocolversion = RORNET_VERSION
        self.terrain         = ""
        self.servername      = ""
        self.passworded      = False
        self.password        = ""
        self.info            = ""

    def update(self, u):
        t = server_info_t()
        if u.terrain != t.terrain:
            self.terrain = u.terrain
        if u.servername != t.servername:
            self.servername = u.servername
        if u.info != t.info:
            self.info = u.info
        del t
