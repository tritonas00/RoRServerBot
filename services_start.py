import threading, time, queue, sys, os, logging, copy
from xml.etree import ElementTree as ET # used to parse xml, for the config file
import RoR_client, Discord_client
import discord
from discord.ext import commands

import logging
logging.basicConfig(
    level=logging.INFO,
    style="{",
    format="{levelname:8s}; {threadName:21s}; {asctime:s}; {name:<15s} {lineno:4d}; {message:s}"
)

# This program allows you to monitor your servers through IRC.
# It can connect to 1..1 IRC server and 1..* RoR servers.

# Main idea of how this works:
# It reads the configuration.xml
# It connects to the IRC server.
# Then it starts the RoR clients, which connect to the RoR servers, specified in the configuration
# It reports what happens in the RoR server to the IRC server, and vice versa
# It exits on request of a global admin on IRC or if it loses connection to IRC
# It will not exit if it loses connection to a (or even all) RoR servers!
# You can restart crashed/stopped RoR clients via the !connect command

class Config:

    def __init__(self, configfile):
        self.logger = logging.getLogger('config')
        self.logger.info("Reading configuration file %s", configfile)

        self.settings = {}

        self.readConfig(configfile)

        # print self.settings

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

                'username': 'services',
                'usertoken': '',
                'userlanguage': 'en_UK',

                'password': '',

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
                        'log_file': 'configuration.xml',
                        'log_level': logging.INFO,
                        'log_filemode': 'w',
                        'version_str': 'RoR server-services v2020.03',
                        'version_num': "2020.03",
                        'clientname': 'RoR_bot',
                },
                'Discordclient': {
                    'token': ''
                },
                'RoRclients': {

                },
        }


        # start processing the configuration.
        # Note: this code is a mess

        # if an element <general> exists
        if not element.find("./general") is None:

            # if an element <remove_this> exists in <general>, then the user didn't read the configuration
            # So we exit without doing anything
            if not element.find("./general/remove_this") is None:
                self.logger.critical("Please fill out the configuration.xml file first!")
                sys.exit(1)

            # if an element <logfile> exists in <general>
            if not element.find("./general/logfile") is None:
                # if an attribute level exists
                tmp = element.find("./general/logfile").get("level", default="")
                if tmp == "debug":
                    self.settings['general']['log_level'] = logging.DEBUG
                elif tmp == "info":
                    self.settings['general']['log_level'] = logging.INFO
                elif tmp == "warning":
                    self.settings['general']['log_level'] = logging.WARNING
                elif tmp == "error":
                    self.settings['general']['log_level'] = logging.ERROR
                elif tmp == "critical":
                    self.settings['general']['log_level'] = logging.CRITICAL
                else:
                    self.logger.warning("Unknown loglevel '%s' in configuration.xml: general/logfile[@level]", tmp)

                # if an attribute append exists
                tmp = element.find("./general/logfile").get("append", default="")
                if tmp == "yes" or tmp == "true" or tmp == "1":
                    self.settings['general']['log_filemode'] = "a"
                elif tmp == "no" or tmp == "false" or tmp == "0":
                    self.settings['general']['log_filemode'] = "w"
                else:
                    self.logger.warning("In configuration.xml: general/logfile[@append] should be yes or no")

                # read the text between the <logfile> tags
                if len(element.find("./general/logfile").text.strip()) > 0:
                    self.settings['general']['log_file'] = element.find("./general/logfile").text.strip()


        # if an element <IRCclient> exists
        if not element.find("./Discordclient") is None:

            if not element.find("./Discordclient/skip_discord") is None:
                print("Discord disabled, skipping connection.")

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
            self.logger.info("   - %s:%d - user: %s - channel %s", self.settings['RoRclients'][RoRclient]['host'], self.settings['RoRclients'][RoRclient]['port'], self.settings['RoRclients'][RoRclient]['username'], self.settings['RoRclients'][RoRclient]['discordchannel'])

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

        if not RoRclient.find("./discord") is None:
            s['discordchannel'] = RoRclient.find("./discord").get("channel", default=s['discordchannel'])
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

class main:

    def __init__(self):

        self.runCondition = True
        self.restarting   = False

        logging.basicConfig(filename='RoRservices.log',level=logging.DEBUG,format="%(asctime)s|%(name)-12s|%(levelname)-8s| %(message)s",filemode="w")
        self.logger = logging.getLogger('main')
        self.logger.info('LOG STARTED')

        self.queue_to_main = queue.Queue()
        self.RoRclients = {}
        self.RoRqueue = {}

        self.settings = Config("configuration.xml")
        self.main_queue = queue.Queue()
        self.queue_Discord_in = queue.Queue()

        # start the Discord bot
        # see https://discordpy.readthedocs.io/en/latest/index.html
        # repo available at https://github.com/Rapptz/discord.py
        self.Discord_bot = commands.Bot(command_prefix='!')
        self.Discord_bot.add_cog(Discord_client.Cg_Cmd(self.Discord_bot))
        #self.Discord_bot.start(self.settings.getSetting('Discordclient', 'token'))
        self.Discord_client = Discord_client.Discord_client(self, self.Discord_bot)
        self.Discord_client.start()

        #time.sleep(2)

        RoRclients_tmp = self.settings.getSetting('RoRclients')
        for ID in list(RoRclients_tmp.keys()):
            self.logger.debug("in iteration, ID=%s", ID)
            self.queue_Discord_in.put(("join", self.settings.getSetting('RoRclients', ID, "discordchannel")))
            self.RoRqueue[ID] = queue.Queue()
            self.RoRclients[ID] = RoR_client.Client(ID, self)
            self.RoRclients[ID].setName('RoR_thread_'+ID)
            self.RoRclients[ID].start()

        self.stayAlive()

    def messageRoRclient(self, ID, data):
        try:
            self.RoRqueue[ID].put_nowait( data )
        except queue.Full:
            self.logger.warning("queue to RoRclient %s is full. Message dropped.", ID)
            return False
        return True

    def messageRoRclientByChannel(self, channel, data):
        self.logger.debug("Inside messageRoRclientByChannel(%s, data)", channel)
        for ID in list(self.settings.getSetting('RoRclients').keys()):
            self.logger.debug("   checking ID %s", ID)
            if self.settings.getSetting('RoRclients', ID, "discordchannel")==channel:
                self.logger.debug("   Channel ok, adding to queue")
                self.messageRoRclient(ID, data)

    def messageDiscordclient(self, data):
        try:
            self.queue_Discord_in.put_nowait( data )
        except queue.Full:
            self.logger.warning("queue to Discordclient is full. Message dropped.")
            return False
        return True

    def messageMain(self, data):
        try:
            self.queue_to_main.put_nowait( data )
        except queue.Full:
            self.logger.warning("queue to main is full. Message dropped.")
            return False
        return True

    def __shutDown(self):
        self.logger.info("Starting global shutdown sequence")
        killCounter = 0
        for ID in self.RoRclients:
            if self.RoRclients[ID].is_alive():
                self.logger.info("   - terminating RoRclient %s" % ID)
                self.messageRoRclient(ID, ("disconnect", self.restarting))
                killCounter += 1
        if killCounter > 0:
            self.logger.info("   - Waiting for RoRclients to disconnect...")
            time.sleep(6)
        else:
            self.logger.error("   x Found no RoRclients running...")

        #TODO: cleanly disconnect from Discord

        for ID in self.RoRclients:
            if self.RoRclients[ID].is_alive():
                self.logger.error("   x Failed to terminate RoRclient %s" % ID)
        self.logger.info("Global shutdown sequence successfully finished.")

        # close loggers:
        logging.shutdown()

        sys.exit(0)

    def stayAlive(self):
        try:
            while self.runCondition:
                try:
                    response = self.queue_to_main.get()
                except queue.Empty:
                    self.logger.error("Main queue timed out.")
                else:
                    if response[0] == "Discord":
                        if response[1] == "connect_success":
                            pass
                        elif response[1] == "connect_failure":
                            self.logger.critical("Couldn't connect to the Discord server.")
                            break
                        elif response[1] == "shut_down":
                            break
                        elif response[1] == "connect":
                            for ID in list(self.settings.getSetting('RoRclients').keys()):
                                if self.settings.getSetting('RoRclients', ID, "discordchannel") == response[2] and not self.RoRclients[ID].is_alive():
                                    self.logger.debug("Starting RoR_client "+ID)
                                    self.queue_Discord_in.put(("join", self.settings.getSetting('RoRclients', ID, "discordchannel")))
                                    self.RoRqueue[ID] = queue.Queue()
                                    self.RoRclients[ID] = RoR_client.Client(ID, self)
                                    self.RoRclients[ID].setName('RoR_thread_'+ID)
                                    self.RoRclients[ID].start()

                        elif response[1] == "serverlist":
                            for ID in list(self.settings.getSetting('RoRclients').keys()):
                                connected = "Not connected"
                                if self.RoRclients[ID].is_alive():
                                    connected = "connected"
                                self.messageIRCclient(("privmsg", response[2], "%-12s | %-21s | %s" % (ID, "%s:%d" % (self.settings.getSetting('RoRclients', ID, 'host'), self.settings.getSetting('RoRclients', ID, 'port')), connected), "syst"))
                        else:
                            self.logger.error("Received an unhandled message from the IRC client.")


                    else:
                        pass

        except(KeyboardInterrupt, SystemExit):
            print("Terminating on demand...")
        self.__shutDown()
        sys.exit(0)

if __name__ == "__main__":
    main = main()