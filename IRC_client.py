#! /usr/bin/env python

#import irclib, threading, sys, logging, Queue, time
#from irclib import nm_to_n, nm_to_h, nm_to_uh, irc_lower
import threading, sys, logging, Queue, time
import ircclient as irclib
from ircclient import nm_to_n, nm_to_h, nm_to_uh, irc_lower

class IRC_users:
	def __init__(self, settings):
		self.reset()
		self.settings = settings
	
	# USER SYSTEM:
	#  - There are 2 main types of users:
	#      - normal users: the default - We don't keep track of these
	#      - admins: There are 4 kinds of admins, see further.
	# ADMIN SYSTEM
	#  - There are 4 types of admins:
	#      - Permanent global admins
	#      - Temporary global admins
	#      - Permanent server admins
	#      - Temporary server admins
	#  - permanent vs temporary admins:
	#      - Permanent admins are defined in the configuration file.
	#      - Temporary admins are added via the addGlobalAdmin or addServerAdmin function
	#        For security considerations, it's possible to disable temporary admins through the configuration file
	#  - Global vs Server admins:
	#      - A global admin has full control over the bot and over all servers
	#        Every global admin is also a server admin
	#      - A server admin has full control over a certain server.
	#  - Notes:
	#      - You should have at least 1 global admin, otherwise, you can't stop the bot (without killing it)
	#      - An admin has alot of power. Screen your users before you make them admin!
	#      - Even though you can delete permanent admins, the deletion is only temporary
	#      - "Temporary" means: "until next restart"


	# This returns true if the user has successfully identified as a global admin
	def isGlobalAdmin(self, nickname):
		if nickname in self.admins['global'].keys():
			return self.admins['global'][nickname]['identified']
		else:
			return False
	
	# This returns true if the user has successfully identified as a global or server admin
	def isServerAdmin(self, nickname, channel):
		if self.isGlobalAdmin(nickname):
			return True
		else:
			if channel in self.admins.keys() and nickname in self.admins[channel].keys():
				return self.admins[channel][nickname]['identified']
			else:
				return False
	
	# This returns true if the password matches the username, else false
	def adminLogIn(self, nickname, username, password, adminType={'adminName': ""}):
		self.adminLogOut(nickname)
		count = 0

		# check serveradmin
		for RoRclient in self.settings.getSetting('RoRclients').keys():
			if username in self.settings.getSetting('RoRclients', RoRclient, 'admins').keys() and self.settings.getSetting('RoRclients', RoRclient, 'admins', username, 'password')==password:
				channel = self.settings.getSetting('RoRclients', RoRclient, 'ircchannel')
				if not channel in self.admins.keys():
					self.admins[channel] = {}
				self.admins[channel][nickname] = {
					'identified': True,
					'username': username,
					'password': password
				}
				adminType['adminName'] = "server admin for server %s in channel %s" % (RoRclient, channel)
				count += 1
		
		if count > 1:
			adminType['adminName'] = "server admin on multiple servers."

		# check global admin
		if username in self.settings.getSetting('general', 'admins').keys() and self.settings.getSetting('general', 'admins', username, 'password')==password:
			self.admins['global'][nickname] = {
				'identified': True,
				'username': username,
				'password': password,
			}
			adminType['adminName'] = "global admin"
			count += 1

		return count > 0
			
	
	# This returns a number greater than 0 if nickname was logged in and successfully logged out
	def adminLogOut(self, nickname, channel=None):
		count = 0
		if channel is None:
			for channel in self.admins.keys():
				if nickname in self.admins[channel].keys():
					self.admins[channel][nickname]['identified'] = False
					count += 1
		else:
			if channel in self.admins.keys():
				if nickname in self.admins[channel].keys():
						self.admins[channel][nickname]['identified'] = False
						count += 1
		return count
			
	
	def nickChange(self, nickname_old, nickname_new):
		# print "old nick=" + nm_to_n(nickname_old) + " and new nick = " + nickname_new
		for channel in self.admins.keys():
			if nickname_old in self.admins[channel].keys():
				self.admins[channel][nickname_new+'!'+nm_to_uh(nickname_old)] = self.admins[channel][nickname_old]
				del self.admins[channel][nickname_old]
			
	def getGlobalAdmins(self):
		return self.admins['global']
	def getAdmins(self):
		return self.admins
	
	def reset(self):
		self.admins = {
			'global': {
				
			}
		}


class IRC_client(threading.Thread):

	def run(self):
		
		self.logger.debug("Starting main loop...")
		reconnectCounter = 100;
		while reconnectCounter>0:
			if not self.connect():
				self.main.messageMain(("IRC", "connect_failure"))
				return

			while 1:
				self.irc.process_once(0.2) # 5 fps
				while not self.main.queue_IRC_in.empty():
					try:
						data = self.main.queue_IRC_in.get_nowait()
						if data[0] == "privmsg":
							self.msg(data[1], data[2], data[3])
						elif data[0] == "join":
							self.server.join(data[1])
							self.logger.debug("joining "+data[1])
						elif data[0] == "disconnect":
							self.disconnect(data[1])
					except Queue.Empty:
						break
				if not self.server.is_connected():
					self.logger.critical("Connection to IRC server lost.")
					#reconnectCounter = 0
					break
			
			time.sleep(5*2**(4-reconnectCounter))
			reconnectCounter -= 1
		
	def connect(self):
		try:
			self.server.connect(
				self.main.settings.getSetting('IRCclient', 'host'),
				self.main.settings.getSetting('IRCclient', 'port'),
				self.main.settings.getSetting('IRCclient', 'nickname'),
				self.main.settings.getSetting('IRCclient', 'password'),
				self.main.settings.getSetting('IRCclient', 'username'),
				self.main.settings.getSetting('IRCclient', 'realname'),
				self.main.settings.getSetting('IRCclient', 'local_address'),
				self.main.settings.getSetting('IRCclient', 'local_port'),
				self.main.settings.getSetting('IRCclient', 'ssl'),
				self.main.settings.getSetting('IRCclient', 'ipv6')
			)
		except irclib.ServerConnectionError:
			return False

		return True

	# def __init__(self, channel, nickname, servername, port, realname):
	def __init__(self, main):
		self.logger = logging.getLogger("IRC")
		self.logger.info("Connecting to IRC server...")
		self.irc = irclib.IRC()
		self.server = self.irc.server()
		self.main = main
		self.users = IRC_users(self.main.settings)
		
		self.logger.debug("Adding global handlers...")
		# add events
		for i in [
			"disconnect",
			"kick",
			"quit",
			"nick",
			"welcome",
			"error",
			"join",
			"mode",
			"part",
			"privmsg",
			"privnotice",
			"pubmsg",
			"pubnotice",
			"invite",
			"ctcp",
			"nicknameinuse",
			"endofmotd"
		]:
			self.irc.add_global_handler(i, getattr(self, "on_" + i))
		
		threading.Thread.__init__(self)
		
	# def on_nicknameinuse(self, c, e):
		# print "Warning: nickname already in use"
		# c.nick(c.get_nickname() + "_")

	########################
	# EVENT HANDLERS START #
	########################
	
	def on_disconnect(self, c, e):
		# event handler: disconnect
		print "disconnected " + e.arguments() [ 0 ]
		self.users.reset()
		
	def on_kick(self, c, e):
		# event handler: kick
		self.users.adminLogOut(e.source(), e.target())
		print "kicked " + e.target() + e.source()
		
	def on_quit(self, c, e):
		# event handler: quit
		self.users.adminLogOut(e.source())
	
	def on_nick(self, c, e):
		# even handler: nick
		# someone changed his nick
		self.users.nickChange(e.source(), e.target())
	
	def on_welcome(self, c, e):
		# event handler: welcome
		print "info: Connected to IRC"
		
		# event handler: endofmotd
		# Get our operator status if applicable
		if len(self.main.settings.getSetting('IRCclient', 'oper_username'))>0 and len(self.main.settings.getSetting('IRCclient', 'oper_password'))>0:
			self.logger.info("Getting our OPER status... '%s'" % self.main.settings.getSetting('IRCclient', 'oper_password'))
			self.server.oper(
				self.main.settings.getSetting('IRCclient', 'oper_username'),
				self.main.settings.getSetting('IRCclient', 'oper_password')
			)
			self.logger.info("'OPER %s %s'" % (self.main.settings.getSetting('IRCclient', 'oper_username'), self.main.settings.getSetting('IRCclient', 'oper_password')));
		
		# Identify ourself with NickServ, if applicable
		if len(self.main.settings.getSetting('IRCclient', 'nickserv_username'))>0 and len(self.main.settings.getSetting('IRCclient', 'nickserv_password'))>0:
			self.logger.info("Identifying with NickServ")
			self.server.privmsg("NickServ", "IDENTIFY %s %s" % (self.main.settings.getSetting('IRCclient', 'nickserv_username'), self.main.settings.getSetting('IRCclient', 'nickserv_password')))

		self.main.messageMain(("IRC", "connect_success"))
	
	def on_error(self, c, e):
		# event handler: error
		self.logger.error("IRC client encountered an error.")
	
	def on_join(self, c, e):
		# event handler: join
		pass
		
	def on_mode(self, c, e):
		# event handler: mode
		# print "info: someone changed mode"
		pass
		
	def on_part(self, c, e):
		# event handler: part
		self.users.adminLogOut(e.source(), e.target())
		print "info: someone left the channel " + e.target()

	def on_privmsg(self, c, e):
		# event handler: privmsg
		self.logger.debug("%s: %s: %s", e.target(), nm_to_n(e.source()), e.arguments()[0])
		self.doCommand(nm_to_n(e.source()), e.source(), e.arguments()[0])
		
	def on_privnotice(self, c, e):
		# event handler: privnotice
		self.logger.debug("%s: %s: %s", e.target(), nm_to_n(e.source()), e.arguments()[0])
		self.doCommand(nm_to_n(e.source()), e.source(), e.arguments()[0])

	def on_pubmsg(self, c, e):
		# event handler: pubmsg
		self.logger.debug("%s: %s: %s", e.target(), nm_to_n(e.source()), e.arguments()[0])
		self.doCommand(irc_lower(e.target()), e.source(), e.arguments()[0])
			
	def on_pubnotice(self, c, e):
		# event handler: pubnotice
		self.logger.debug("%s: %s: %s", e.target(), nm_to_n(e.source()), e.arguments()[0])
		self.doCommand(irc_lower(e.target()), e.source(), e.arguments()[0])
		
	def on_invite(self, c, e):
		# event handler: invite
		print "info: invite: " + e.arguments()[0]
	
	def on_ctcp(self, c, e):
		# event handler: ctcp
		if e.arguments()[0] == "VERSION":
			c.ctcp_reply(nm_to_n(e.source()),
				"VERSION " + "Rigs Of Rods server services and monitoring robot v" + self.main.settings.getSetting('general', 'version_str'))
		elif e.arguments()[0] == "PING":
			if len(e.arguments()) > 1:
				c.ctcp_reply(nm_to_n(e.source()),
					"PING " + e.arguments()[1])
		
	def on_nicknameinuse(self, c, e):
		# event handler: nicknameinuse
		pass
	
	def on_endofmotd(self, c, e):
		# event handler: endofmotd
		# Get our operator status if applicable
		if len(self.main.settings.getSetting('IRCclient', 'oper_username'))>0 and len(self.main.settings.getSetting('IRCclient', 'oper_password'))>0:
			self.logger.info("Getting our OPER status... '%s'" % self.main.settings.getSetting('IRCclient', 'oper_password'))
			self.server.oper(
				self.main.settings.getSetting('IRCclient', 'oper_username'),
				self.main.settings.getSetting('IRCclient', 'oper_password')
			)
			self.logger.info("'OPER %s %s'" % (self.main.settings.getSetting('IRCclient', 'oper_username'), self.main.settings.getSetting('IRCclient', 'oper_password')));
		
		# Identify ourself with NickServ, if applicable
		if len(self.main.settings.getSetting('IRCclient', 'nickserv_username'))>0 and len(self.main.settings.getSetting('IRCclient', 'nickserv_password'))>0:
			self.logger.info("Identifying with NickServ")
			self.server.privmsg("NickServ", "IDENTIFY %s %s" % (self.main.settings.getSetting('IRCclient', 'nickserv_username'), self.main.settings.getSetting('IRCclient', 'nickserv_password')))

		self.main.messageMain(("IRC", "connect_success"))
	
	########################
	# EVENT HANDLERS END   #
	########################
	
	########################
	#  OTHER THINGS START  #
	########################
	
	# Always use a prefix!
	def msg(self, channel, msg, prefix=None):
		if prefix is None:
			self.logger.debug("%s: %s: %s", channel, self.server.get_nickname(), msg)
			self.server.privmsg(channel, msg)
		else:
			self.logger.debug("%s: %s: [%s] %s", channel, self.server.get_nickname(), prefix, msg)
			self.server.privmsg(channel, "%c14[%s]%c %s" % (3, prefix, 15, msg))
	
	def notice(self, target, msg, prefix=None):
		if prefix is None:
			self.logger.debug("%s: %s: %s", target, self.server.get_nickname(), msg)
			self.server.notice(target, msg)
		else:
			self.logger.debug("%s: %s: [%s] %s", target, self.server.get_nickname(), prefix, msg)
			self.server.notice(target, "%c14[%s]%c %s" % (3, prefix, 15, msg))
		
	def say(self, channel, msg):
		print "saying " + msg + " in " + channel
		# self.server.privmsg(channel, msg)
	
	def disconnect(self, msg="Error"):
		self.logger.info("disconnecting on request: %s" % msg)
		self.irc.disconnect_all(msg)
		self.server.close()
		sys.exit(0)
	
	def is_connected(self):
		return self.server.is_connected()
	
	def doCommand(self, channel, source, cmd):
		nickname = nm_to_n(source)
		a = cmd.split(" ", 1)
		a[0] = irc_lower(a[0].strip())

		if a[0] == "!rawmsg":
			# server-admin only
			# send a chat message on the server
			if self.users.isServerAdmin(source, channel):
				if len(a)>1:
					self.main.messageRoRclientByChannel(channel, ("msg", a[1]))
			else:
				self.msg(channel, "You have no permission to use this command!", "syst")
		elif a[0] == "!rawcmd":
			# server-admin only
			# send a chat message on the server
			if self.users.isServerAdmin(source, channel):
				if len(a)>1:
					self.main.messageRoRclientByChannel(channel, ("cmd", a[1]))
			else:
				self.msg(channel, "You have no permission to use this command!", "syst")
		elif a[0] == "!msg":
			# send a chat message on the server
			if self.users.isServerAdmin(source, channel):
				if len(a)>1:
					self.main.messageRoRclientByChannel(channel, ("msg_with_source", a[1], nickname))
			else:
				self.msg(channel, "You have no permission to use this command!", "syst")
		elif a[0] == "!op":
			# send a chat message on the server
			if self.users.isServerAdmin(source, channel):
				if len(a)>1:
					self.server.send_raw("mode "+channel+" +o "+ a[1].lower())
					self.notice(nickname, "'"+a[1]+"' is now a channel operator.", "syst")
					#self.notice(nickname, "mode "+channel+" +o "+ a[1].lower(), "syst")
				else:
					if nickname.lower() != 'lannii':
						self.server.send_raw("mode "+channel+" +o "+ nickname.lower())
						self.notice(nickname, "You are now a channel operator.", "syst")
						#self.notice(nickname, "mode "+channel+" +o "+ nickname.lower(), "syst")
					else:
						self.notice(nickname, "You are already a channel operator.", "syst")
			else:
				self.msg(channel, "You have no permission to use this command!", "syst")
		elif a[0] == "!privmsg":
			# server-admin only
			# send a private chat message on the RoR server
			if self.users.isServerAdmin(source, channel):
				if len(a) < 2:
					self.msg(channel, "Syntax: !privmsg <uid> <message>", "syst")
				else:
					args = a[1].split(" ", 1)
					if len(args) >= 1:
						try:
							args[0] = int(args[0])
						except ValueError:
							self.msg(channel, "Syntax: !privmsg <uid> <message>", "syst")
						else:
							if len(args) ==2:
								self.main.messageRoRclientByChannel(channel, ("privmsg", args[0], args[1]))
							else:
								self.msg(channel, "Syntax: !privmsg <uid> <message>", "syst")
					else:
						self.msg(channel, "Syntax: !privmsg <uid> <message>", "syst")
			else:
				self.msg(channel, "You have no permission to use this command!", "syst")
		elif a[0] == "!say":
			# server-admin only
			# send a chat message on the server, coming from 'host'
			if self.users.isServerAdmin(source, channel):
				if len(a) < 2:
					self.msg(channel, "Syntax: !say [uid] <message>", "syst")
				else:
					args = a[1].split(" ", 1)
					if len(args) >= 1:
						try:
							args[0] = int(args[0])
						except ValueError:
							self.main.messageRoRclientByChannel(channel, ("say", -1, a[1]))
						else:
							if len(args) ==2:
								self.main.messageRoRclientByChannel(channel, ("say", args[0], args[1]))
							else:
								self.msg(channel, "Syntax: !say [uid] <message>", "syst")
					else:
						self.msg(channel, "Syntax: !say [uid] <message>", "syst")
			else:
				self.msg(channel, "You have no permission to use this command!", "syst")
			
		# elif a[0] == "!disconnect":
			# self.msg(channel, "Disconnecting on request...", "syst")
			# self.disconnect("As requested by %s" % nickname)
		elif a[0] == "!shutdown":
			# global-admin only
			# Shut down everything
			if self.users.isGlobalAdmin(source):
				self.msg(channel, "Initiating shutdown sequence...", "syst")
				self.main.messageMain(("IRC", "shut_down"))
			else:
				self.msg(channel, "You have no permission to use this command!", "syst")
		elif a[0] == "!join":
			# global-admin only
			# join a channel on IRC
			if self.users.isGlobalAdmin(source):
				if len(a)>1:
					self.server.join(a[1])
			else:
				self.msg(channel, "You have no permission to use this command!", "syst")
		elif a[0] == "!leave":
			# global-admin only
			# leave a channel on IRC
			if self.users.isGlobalAdmin(source):
				if len(a)>1:
					self.server.part(a[1])
			else:
				self.msg(channel, "You have no permission to use this command!", "syst")
		elif a[0] == "!ping":
			# Easy command to check if the bot is online
			# (especially useful if you're using a znc)
			self.msg(channel, "pong", "funn")
		elif a[0] == "!kick":
			# server-admin only
			# kicks a player from the server
			if self.users.isServerAdmin(source, channel):
				if len(a) < 2:
					self.msg(channel, "Syntax: !kick <uid> [reason]", "syst")
				else:			
					args = a[1].split(" ", 1)
					if len(args) >= 1:
						try:
							args[0] = int(args[0])
						except ValueError:
							self.msg(channel, "Syntax error, first parameter should be numeric (unique ID of user)", "syst")
						else:
							if len(args) ==2:
								self.main.messageRoRclientByChannel(channel, ("kick", args[0], args[1]))
							elif len(args) ==1:
								self.main.messageRoRclientByChannel(channel, ("kick", args[0], "an unspecified reason"))
					else:
						self.msg(channel, "Syntax: !kick <uid> [reason]", "syst")
			else:
				self.msg(channel, "You have no permission to use this command!", "syst")

		elif a[0] == "!ban":
			# server-admin only
			# bans a player from the server	
			if self.users.isServerAdmin(source, channel):
				if len(a) < 2:
					self.msg(channel, "Syntax: !ban <uid> [reason]", "syst")
				else:			
					args = a[1].split(" ", 1)
					if len(args) >= 1:
						try:
							args[0] = int(args[0])
						except ValueError:
							self.msg(channel, "Syntax error, first parameter should be numeric (unique ID of user)", "syst")
						else:
							if len(args) ==2:
								self.main.messageRoRclientByChannel(channel, ("ban", args[0], args[1]))
							elif len(args) ==1:
								self.main.messageRoRclientByChannel(channel, ("ban", args[0], "an unspecified reason"))
					else:
						self.msg(channel, "Syntax: !ban <uid> [reason]", "syst")
			else:
				self.msg(channel, "You have no permission to use this command!", "syst")
	
		elif a[0] == "!bans":
			# server-admin only
			# view currently banned people
			self.main.messageRoRclientByChannel(channel, ("msg", "!bans"))
		elif a[0] == "!list" :
			# returns a list of the players ingame
			self.main.messageRoRclientByChannel(channel, ("msg", "!list"))
		elif a[0] == "!pl" or a[0]=="!playerlist":
			self.main.messageRoRclientByChannel(channel, ("list_players",))
		elif a[0] == "!info" or a[0] == "!gi":
			# returns the server info (name, ip, port, terrain, players, ...)
			self.main.messageRoRclientByChannel(channel, ("info", "full"))
		elif a[0] == "!stats":
			self.main.messageRoRclientByChannel(channel, ("global_stats",))
		elif a[0] == "!pinfo" or a[0] == "!pi" or a[0] == "!playerinfo":
			# returns the player info
				if len(a) < 2:
					self.msg(channel, "Syntax: !pi <uid>", "syst")
				else:			
					try:
						a[1] = int(a[1])
					except ValueError:
						self.msg(channel, "Syntax error, first parameter should be numeric (unique ID of user)", "syst")
					else:
						self.main.messageRoRclientByChannel(channel, ("player_info", a[1]))
		elif a[0] == "!terrain":
			# returns the server info (name, terrain, players)
			self.main.messageRoRclientByChannel(channel, ("info", "short"))
		elif a[0] == "!ip" or a[0] == "!serverinfo" or a[0] == "!si":
			# returns the server name, ip and port
			self.main.messageRoRclientByChannel(channel, ("info", "ip"))
		elif a[0] == "!warn":
			# server-admin only
			# send a warning to a user
			if self.users.isServerAdmin(source, channel):
				if len(a) < 2:
					self.msg(channel, "Syntax: !warn <uid> [reason]", "syst")
				else:
					args = a[1].split(" ", 1)
					if len(args) >= 1:
						try:
							args[0] = int(args[0])
						except ValueError:
							self.msg(channel, "Syntax error, first parameter should be numeric (unique ID of user)", "syst")
						else:
							if len(args) ==2:
								self.main.messageRoRclientByChannel(channel, ("say", args[0], args[1]))
							elif len(args) ==1:
								self.main.messageRoRclientByChannel(channel, ("say", args[0], "This is an official warning. Please read our rules using the !rules command."))
					else:
						self.msg(channel, "Syntax: !warn <uid> [reason]", "syst")
			else:
				self.msg(channel, "You have no permission to use this command!", "syst")
		elif a[0] == "!disconnect":
			# server-admin only
			# disconnects from the a RoR server
			if self.users.isServerAdmin(source, channel):
				self.main.messageRoRclientByChannel(channel, ("disconnect", "Leaving server..."))
			else:
				self.msg(channel, "You have no permission to use this command!", "syst")
		elif a[0] == "!connect":
			# server-admin only
			# connect to a RoR server
			if self.users.isServerAdmin(source, channel):
				self.main.messageMain(("IRC", "connect", channel))
			else:
				self.msg(channel, "You have no permission to use this command!", "syst")
		elif a[0] == "!serverlist" or a[0] == "!servlist":
			# returns a list of RoR servers we're connected to (with ID, name, ip and port) CIFPO_serv | servername | players/maxplayers | online
			if self.users.isGlobalAdmin(source):
				self.main.messageMain(("IRC", "serverlist", channel))
			else:
				self.msg(channel, "You have no permission to use this command!", "syst")
		elif a[0] == "identify":
			if channel == nickname:
				if len(a) < 2:
					self.notice(nickname, "Syntax: /msg %s IDENTIFY <username> <password>" % self.server.get_nickname(), "syst")
				else:
					args = a[1].split(" ")
					adminType = { 'adminName': "" }
					if len(args) >= 2 and self.users.adminLogIn(source, args[0], args[1], adminType):
						self.notice(nickname, "You are now identified as %s" % adminType['adminName'], "syst")
					elif len(args) >= 2:
						self.notice(nickname, "This user/password combination does not exist.", "syst")
					else:
						self.notice(nickname, "Syntax: /msg %s IDENTIFY <username> <password>" % self.server.get_nickname(), "syst")
	
		elif a[0] == "logout":
			if channel == nickname:
				if self.users.adminLogOut(source):
					self.notice(nickname, "You are now logged out.", "syst")
				else:
					self.notice(nickname, "You weren't logged in :/", "syst")
	
		elif a[0] == "!admins":
			if self.users.isGlobalAdmin(source):
				admins = self.users.getAdmins()
				self.notice(nickname, "nickname   | username   | channel", "syst")
				for type in admins.keys():
					for nick in admins[type].keys():
						if admins[type][nick]['identified']:
							self.notice(nickname, "%-11s| %-11s| %s" % (nm_to_n(nick), admins[type][nick]['username'], type), "syst")
			else:
				self.notice(nickname, "Please login first.", "syst")
		elif a[0] == "!fps":
			self.main.messageRoRclientByChannel(channel, ("fps", ""))

if __name__ == "__main__":
	print "Don't start this directly! Start services_start.py"
