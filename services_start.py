import threading, time, queue, sys, os, logging, copy
from xml.etree import ElementTree as ET # used to parse xml, for the config file
import RoR_client
import discord
from discord.ext.tasks import loop
import asyncio

import logging
logging.basicConfig(
    level=logging.ERROR,
    style="{",
    format="{levelname:8s}; {threadName:21s}; {asctime:s}; {name:<15s} {lineno:4d}; {message:s}"
)

# Main idea of how this works:
# It reads the configuration.xml
# Then it starts the RoR clients, which connect to the RoR servers, specified in the configuration
# It will not exit if it loses connection to a (or even all) RoR servers!
# You can restart crashed/stopped RoR clients via the !connect command

class Config:

    def __init__(self, configfile):
        self.logger = logging.getLogger('config')
        self.logger.info("Reading configuration file %s", configfile)

        self.settings = {}

        self.readConfig(configfile)

        self.logger.debug("Configuration read.")

    def readConfig(self, configfile):
        # get the path to the file
        xml_file = os.path.abspath(__file__)
        xml_file = os.path.dirname(xml_file)
        xml_file = os.path.join(xml_file, configfile)

        # parse the file
        try:
            tree = ET.parse(xml_file)
        except Exception as inst:
            self.logger.critical("Unexpected error opening %s: %s" % (xml_file, inst))
            sys.exit(1)

        # now, we can start processing data
        # I chose to check every tag, so errors in the \
        # configuration file are more likely to get noticed
        element = tree.getroot()


        # A RoRclient template.
        # This will be changed to the user-defined template later on
        defaultRoRclient = {
                'ID': None,

                'host': None,
                'port': 0,
                'password': '',

                'username': 'services',
                'usertoken': '',
                'userlanguage': 'en_UK',

                'discordchannel': None,

                'announcementsEnabled': False,
                'announcementsDelay': 300,
                'announcementList': {
                        # 'announcementNumber': {
                                # 'text': '',
                        # },
                },

                'reconnection_interval': 5,
                'reconnection_tries': 3,
        }

        # Fill the whole settings dictionary with default values
        self.settings = {
                'general': {
                        'version_str': 'RoR server-services v2021.04',
                        'version_num': "2021.04",
                        'clientname': 'RoR_bot',
                },
                'Discordclient': {
                    'token': '',
                },
                'RoRclients': {

                },
        }


        # start processing the configuration.

        # if an element <Discordclient> exists
        if not element.find("./Discordclient") is None:

            # if an element <bot> exists in <Discordclient>
            if not element.find("./Discordclient/bot") is None:
                self.settings['Discordclient']['token'] = element.find("Discordclient/bot").get("token")
            else:
                self.logger.critical("In configuration.xml: Discordclient/bot needs to be set!")
                sys.exit(1)
        else:
            self.logger.critical("No Discordclient section found!")
            sys.exit(1)

        # if an element <RoRclients> exists
        if not element.find("./RoRclients") is None:
            RoRclients = element.find("./RoRclients")
            id = 0

            # search for an element with id="default/template"
            for RoRclient in RoRclients:
                if RoRclient.get("id", default="")=="default/template":
                    self.logger.info("Parsing template-RoRclient 'default/template'")
                    self.parseRoRclient("default/template", RoRclient, defaultRoRclient)
                    break

            for RoRclient in RoRclients:

                # get/generate an ID
                if not RoRclient.get("id") is None:
                    ID = RoRclient.get("id")
                else:
                    ID = "RoR %d" % id

                if RoRclient.get("id", default="")=="default/template":
                    continue

                if not RoRclient.get("enabled") is None:
                    if RoRclient.get("enabled") != "yes" and RoRclient.get("enabled") != "true" and RoRclient.get("enabled") != "1":
                        self.logger.info("RoRclient %s skipped. Disabled on request.", ID)
                        continue
                if not RoRclient.get("disabled") is None:
                    if RoRclient.get("disabled") == "yes" or RoRclient.get("disabled") == "true" or RoRclient.get("disabled") == "1":
                        self.logger.info("RoRclient %s skipped. Disabled on request.", ID)
                        continue

                id += 1

                self.settings['RoRclients'][ID] = copy.deepcopy(defaultRoRclient)
                self.settings['RoRclients'][ID]['ID'] = ID
                if not self.parseRoRclient(ID, RoRclient, self.settings['RoRclients'][ID]):
                    del self.settings['RoRclients'][ID]


            if len(self.settings['RoRclients'])<=0:
                self.logger.critical("No 'RoRclient' elements found in the configuration file.")
                sys.exit(1)
            del RoRclients
        else:
            self.logger.critical("No RoRclients section found!")
            sys.exit(1)

        del tree, xml_file, element, defaultRoRclient

        # log some things
        self.logger.info("Successfully parsed the following servers:")
        for RoRclient in self.settings['RoRclients']:
            self.logger.info("   - %s:%d - user: %s - channel %s ", self.settings['RoRclients'][RoRclient]['host'], self.settings['RoRclients'][RoRclient]['port'], self.settings['RoRclients'][RoRclient]['username'], self.settings['RoRclients'][RoRclient]['discordchannel'])

    def parseRoRclient(self, ID, RoRclient, s):

        # if an element <server> exists
        if not RoRclient.find("./server") is None:
            s['host']     = RoRclient.find("./server").get("host", default=s['host'])
            s['port'] = int(RoRclient.find("./server").get("port", default=s['port']))
            s['password'] = RoRclient.find("./server").get("password", default=s['password'])
        if ( s['host'] is None or s['port']==0 ) and ID != "default/template":
            self.logger.error("configuration/RoRclients/RoRclient(%s)/server[@host, @port] needs to be set!", ID)
            self.logger.error("Ignoring RoRclient(%s)", ID)
            return False


        # if an element <discord> exists
        if not RoRclient.find("./discord") is None:
            s['discordchannel'] = RoRclient.find("./discord").get("channel", default=s['discordchannel']).lower()
        if ( RoRclient.find("./discord") is None or s['discordchannel'] is None ) and ID != "default/template":
            self.logger.error("configuration/RoRclients/RoRclient(%s)/discord[@channel] needs to be set!", ID)
            self.logger.error("Ignoring RoRclient(%s)", ID)
            return False

        # if an element <user> exists
        if not RoRclient.find("./user") is None:
            s['username']     = RoRclient.find("./user").get("name", default=s['username'])
            s['usertoken']    = RoRclient.find("./user").get("token", default=s['usertoken'])
            s['userlanguage'] = RoRclient.find("./user").get("language", default=s['userlanguage'])

        # if an element <announcements> exists
        if not RoRclient.find("./announcements") is None:
            announcements = RoRclient.find("./announcements")

            s['announcementsDelay'] = int(announcements.get("delay", default=s['announcementsDelay']))

            counter = 0
            for announcement in announcements:
                s['announcementList'][counter] = announcement.text
                counter += 1

            if counter == 0:
                s['announcementsEnabled'] = False
            else:
                s['announcementsEnabled'] = True

            if not announcements.get("enabled") is None:
                if announcements.get("enabled") != "yes" and announcements.get("enabled") != "true" and announcements.get("enabled") != "1":
                    self.logger.info("Announcements of %s disabled on request.", ID)
                    s['announcementsEnabled'] = False

        return True

    def getSetting(self, A, B=None, C=None, D=None, E=None):
        try:
            if not A is None:
                if not B is None:
                    if not C is None:
                        if not D is None:
                            if not E is None:
                                return self.settings[A][B][C][D][E]
                            else:
                                return self.settings[A][B][C][D]
                        else:
                            return self.settings[A][B][C]
                    else:
                        return self.settings[A][B]
                else:
                    return self.settings[A]
            else:
                self.logger.error("getSetting called without any arguments!")
                return None
        except KeyError:
            if not A is None:
                if not B is None:
                    if not C is None:
                        if not D is None:
                            if not E is None:
                                self.logger.exception("Setting did not exist in Config.getSetting('%s', '%s', '%s', '%s', '%s')", A, B, C, D, E)
                            else:
                                self.logger.exception("Setting did not exist in Config.getSetting('%s', '%s', '%s', '%s')", A, B, C, D)
                        else:
                            self.logger.exception("Setting did not exist in Config.getSetting('%s', '%s', '%s')", A, B, C)
                    else:
                        self.logger.exception("Setting did not exist in Config.getSetting('%s', '%s')", A, B)
                else:
                    self.logger.exception("Setting did not exist in Config.getSetting('%s')", A)
            else:
                self.logger.error("getSetting called without any arguments!")
            return None

class Main(discord.Client):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.logger = logging.getLogger('main')
        self.logger.info('LOG STARTED')

        self.queue_to_main = queue.Queue()
        self.RoRclients = {}
        self.RoRqueue = {}

        self.main_queue = queue.Queue()
        self.settings = Config("configuration.xml")

        self.initialised = False

    def messageRoRclient(self, ID, data):
        try:
            self.RoRqueue[ID].put_nowait( data )
        except queue.Full:
            self.logger.warning("queue to RoRclient %s is full. Message dropped.", ID)
            return False
        return True

    def messageRoRclientByChannel(self, channel, data):
        self.logger.debug("Inside messageRoRclientByChannel(%s, data)", str(channel))
        for ID in self.settings.getSetting('RoRclients').keys():
            self.logger.debug("   checking ID %s", ID)
            if self.settings.getSetting('RoRclients', ID, "discordchannel") == str(channel):
                self.logger.debug("   Channel ok, adding to queue")
                self.messageRoRclient(ID, data)

    def messageMain(self, data):
        try:
            self.queue_to_main.put_nowait( data )
        except queue.Full:
            self.logger.warning("queue to main is full. Message dropped.")
            return False
        return True

    def messageDiscordclient(self, cid, message):
        channel = bot.get_channel(int(cid))
        asyncio.run_coroutine_threadsafe(channel.send(message), bot.loop)

    def checkDiscordChannel(self, cid):
        for RID in list(self.settings.getSetting('RoRclients').keys()):
            if self.settings.getSetting('RoRclients', RID, "discordchannel") == str(cid):
                return True
        return False

    def startRoRclientOnDemand(self, channel):
        RoRclients_tmp = self.settings.getSetting('RoRclients')
        for ID in list(RoRclients_tmp.keys()):
            if self.settings.getSetting('RoRclients', ID, "discordchannel") == str(channel) and not self.RoRclients[ID].is_alive():
                self.logger.debug("in iteration, ID=%s", ID)
                self.RoRqueue[ID] = queue.Queue()
                self.RoRclients[ID] = RoR_client.Client(ID, self)
                self.RoRclients[ID].setName('RoR_thread_'+ID)
                self.RoRclients[ID].start()

    def serverlist(self, cid):
        channel = bot.get_channel(int(cid))
        RoRclients_tmp = self.settings.getSetting('RoRclients')
        for ID in list(RoRclients_tmp.keys()):
            if self.RoRclients[ID].is_alive():
                asyncio.run_coroutine_threadsafe(channel.send("[info] Connected to %s" % ID), bot.loop)
            else:
                asyncio.run_coroutine_threadsafe(channel.send("[info] Disconnected from %s" % ID), bot.loop)

    async def on_ready(self):
        print ("Connected to Discord")

        if not self.initialised:
            RoRclients_tmp = self.settings.getSetting('RoRclients')
            for ID in list(RoRclients_tmp.keys()):
                self.logger.debug("in iteration, ID=%s", ID)
                self.RoRqueue[ID] = queue.Queue()
                self.RoRclients[ID] = RoR_client.Client(ID, self)
                self.RoRclients[ID].setName('RoR_thread_'+ID)
                self.RoRclients[ID].start()
            self.initialised = True

    async def close(self):
        self.logger.info("Starting global shutdown sequence")
        killCounter = 0
        for ID in self.RoRclients:
            if self.RoRclients[ID].is_alive():
                self.logger.info("   - terminating RoRclient %s" % ID)
                self.messageRoRclient(ID, ("disconnect", False))
                killCounter += 1
        if killCounter > 0:
            self.logger.info("   - Waiting for RoRclients to disconnect...")
            time.sleep(6)
        else:
            self.logger.error("   x Found no RoRclients running...")

        for ID in self.RoRclients:
            if self.RoRclients[ID].is_alive():
                self.logger.error("   x Failed to terminate RoRclient %s" % ID)
        self.logger.info("Global shutdown sequence successfully finished.")

        # close loggers:
        logging.shutdown()
        await super().close()
        
bot = Main()

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if message.content.startswith('!list'):
        bot.messageRoRclientByChannel(message.channel.id, ("msg", "!list"))

    if message.content.startswith('!bans'):
        bot.messageRoRclientByChannel(message.channel.id, ("msg", "!bans"))

    if message.content.startswith('!playerlist'):
        bot.messageRoRclientByChannel(message.channel.id, ("list_players",))

    if message.content.startswith('!info'):
        bot.messageRoRclientByChannel(message.channel.id, ("info", "full"))

    if message.content.startswith('!msg'):
        bot.messageRoRclientByChannel(message.channel.id, ("msg_with_source", message.content.replace('!msg' , ''), message.author))

    if message.content.startswith('!rawmsg'):
        bot.messageRoRclientByChannel(message.channel.id, ("msg", message.content.replace('!rawmsg ' , '')))

    if message.content.startswith('!disconnect'):
        bot.messageRoRclientByChannel(message.channel.id, ("disconnect", "Leaving server..."))

    if message.content.startswith('!connect'):
        bot.startRoRclientOnDemand(message.channel.id)

    if message.content.startswith('!shutdown') and bot.checkDiscordChannel(message.channel.id):
        await message.channel.send('[info] Shutting down...')
        await bot.close()

    if message.content.startswith('!kick'):
        args = message.content.split(" ", 2)

        if len(args) == 3:
            bot.messageRoRclientByChannel(message.channel.id, ("kick", int(args[1]), args[2]))
        elif len(args) == 2:
            bot.messageRoRclientByChannel(message.channel.id, ("kick", int(args[1]), "an unspecified reason"))
        elif bot.checkDiscordChannel(message.channel.id):
            await message.channel.send('[info] Syntax: !kick <uid> [reason]')

    if message.content.startswith('!ban'):
        args = message.content.split(" ", 2)

        if len(args) == 3:
            bot.messageRoRclientByChannel(message.channel.id, ("ban", int(args[1]), args[2]))
        elif len(args) == 2:
            bot.messageRoRclientByChannel(message.channel.id, ("ban", int(args[1]), "an unspecified reason"))
        elif bot.checkDiscordChannel(message.channel.id):
            await message.channel.send('[info] Syntax: !ban <uid> [reason]')

    if message.content.startswith('!warn'):
        args = message.content.split(" ", 2)

        if len(args) == 3:
            bot.messageRoRclientByChannel(message.channel.id, ("say", int(args[1]), args[2]))
        elif len(args) == 2:
            bot.messageRoRclientByChannel(message.channel.id, ("say", int(args[1]), "This is an official warning. Please read our rules using the !rules command."))
        elif bot.checkDiscordChannel(message.channel.id):
            await message.channel.send('[info] Syntax: !warn <uid> [reason]')

    if message.content.startswith('!say'):
        args = message.content.split(" ", 2)

        if len(args) == 3:
            bot.messageRoRclientByChannel(message.channel.id, ("say", int(args[1]), args[2]))
        elif len(args) == 2:
            bot.messageRoRclientByChannel(message.channel.id, ("say", int(-1), args[1]))
        elif bot.checkDiscordChannel(message.channel.id):
            await message.channel.send('[info] Syntax: !say [message] or !say <uid> [message]')

    if message.content.startswith('!unban'):
        bot.messageRoRclientByChannel(message.channel.id, ("msg", message.content))

    if message.content.startswith('!stats'):
        bot.messageRoRclientByChannel(message.channel.id, ("global_stats",))

    if message.content.startswith('!fps'):
        bot.messageRoRclientByChannel(message.channel.id, ("fps",))

    if message.content.startswith('!serverlist') and bot.checkDiscordChannel(message.channel.id):
        bot.serverlist(message.channel.id)

    if message.content.startswith('!help') and bot.checkDiscordChannel(message.channel.id):
        str = """
**!connect** Connects to a RoR server. Useful in the event of a server crash
**!disconnect** Disconnects from a RoR server
**!shutdown** Disconnects from all servers and closes the bot
**!msg** Sends a message to the server. Includes your Discord username
**!rawmsg** Sends a message to the server as the bot. Can also be used for some in-game commands
**!say** Sends a message as the host. Can be used to privately message players
**!playerlist** Displays player list with current vehicles
**!list** Displays a simplified player list (useful if you just need the UID)
**!warn** Sends a private warning message to a player. If no message is specified, (This is an official warning. Please read our rules using the !rules command.) will be sent instead
**!kick** Kicks a user
**!ban** Bans a user
**!bans** Displays current banned users
**!unban** Unbans a user
**!rawmsg !unban** Unbans a user
**!info** Returns server info
**!stats** Returns various server stats. May not be accurate
**!serverlist** Returns a list of servers the bot is connected to
**!fps** Returns current bot FPS"""

        await message.channel.send(str)


bot.run(bot.settings.getSetting("Discordclient", "token"))
