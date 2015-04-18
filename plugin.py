###
# Copyright (c) 2013, Richard Esplin
# Based on ChannelLogger by Jeremiah Fincher (c) 2005 and James McCoy (c) 2010
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
###
'''
Channel Logger that produces HTML files.
'''

import os
import re
import sys
import shutil
import time

if sys.version_info[0] >= 3:
    from html import escape as html_escape
    bin_mode = ''
else:
    from xml.sax.saxutils import escape as html_escape
    from io import open
    bin_mode = 'b'

import supybot.conf as conf
import supybot.world as world
import supybot.ircdb as ircdb
import supybot.irclib as irclib
import supybot.ircmsgs as ircmsgs
import supybot.ircutils as ircutils
import supybot.registry as registry
import supybot.callbacks as callbacks
import supybot.commands as commands
try:
    from supybot.i18n import PluginInternationalization, internationalizeDocstring
    _ = PluginInternationalization('HtmlLogger')
except:
    # This are useless functions that's allow to run the plugin on a bot
    # without the i18n plugin
    _ = lambda x:x
    internationalizeDocstring = lambda x:x

# This regex doesn't match every URL, but it is simple and gets most.
url_regex = re.compile("(\s*)([fhtps]{3,5}://\S+)(\s*)")

file_prefix = "log"
file_suffix = "html"
row_class = "style-row"
notice_class = "style-notice"
timestamp_class = "style-tz"
nick_class = "style-nick"
message_class = "style-msg"

class FakeLog(object):
    def flush(self):
        return
    def close(self):
        return
    def write(self, s):
        return

class HtmlLogger(callbacks.Plugin):
    noIgnore = True
    def __init__(self, irc):
        self.__parent = super(HtmlLogger, self)
        self.__parent.__init__(irc)
        self.lastMsgs = {}
        self.lastStates = {}
        self.logs = {}
        self.flusher = self.flush
        world.flushers.append(self.flusher)

    def die(self):
        self.log.debug('Logging is dying.')
        for log in self._logs():
            self.endLog(log)
        world.flushers = [x for x in world.flushers if x is not self.flusher]

    def __call__(self, irc, msg):
        try:
            # I don't know why I put this in, but it doesn't work, because it
            # doesn't call doNick or doQuit.
            # if msg.args and irc.isChannel(msg.args[0]):
            self.__parent.__call__(irc, msg)
            if irc in self.lastMsgs:
                if irc not in self.lastStates:
                    self.lastStates[irc] = irc.state.copy()
                self.lastStates[irc].addMsg(irc, self.lastMsgs[irc])
        finally:
            # We must make sure this always gets updated.
            self.lastMsgs[irc] = msg

    def reset(self):
        self.log.debug('Reset all logs.')
        for log in self._logs():
            self.endLog(log)
        self.logs.clear()
        self.lastMsgs.clear()
        self.lastStates.clear()

    def _logs(self):
        for logs in self.logs.values():
            for log in logs.values():
                yield log

    def getTemplatePath(self, template_name):
        registry_value = ''
        default_name = ''
        if template_name == 'header':
            registry_value = 'headerFile'
            default_name = 'header.html'
        elif template_name == 'footer':
            registry_value = 'footerFile'
            default_name = 'footer.html'
        if template_name == 'indexHeader':
            registry_value = 'indexHeaderFile'
            default_name = 'header.html'
        elif template_name == 'indexFooter':
            registry_value = 'indexFooterFile'
            default_name = 'footer.html'
        templatePath = self.registryValue(registry_value)
        if templatePath == '':
            templatePath = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                                                        default_name)
        return templatePath

    def channel2URL(self, channel_name):
        ''' Some characters are not allowed in URLs, and so must be
            substituted.
            Every reference to the log file name should be processed by this
            function so that the log file can be linked in the URL.
        '''
        urlFriendly = channel_name
        # The hash character in the last segment of a URL directs the browser to
        # an anchor in the page.
        if channel_name.startswith('##'):
            urlFriendly = channel_name.replace('##', 'hashhash-', 1)
        elif channel_name.startswith('#'):
            urlFriendly = channel_name.replace('#', 'hash-', 1)
        return urlFriendly

    def startLog(self, logPath, channel):
        self.log.info('Starting new log file: %s.' % logPath)
        templatePath = self.getTemplatePath('header')
        self.log.debug('Using header template from %s.' % templatePath)
        shutil.copyfile(templatePath, logPath)
        with open(logPath, encoding='utf-8', mode='a'+bin_mode) as logFile:
            logFile.write("<h2>Daily Log for %s</h2>\n" %(channel))

    def generateIndex(self, logDir, channel):
        self.log.info('Generating a new index.html in %s.' % logDir)
        templatePath = self.getTemplatePath('indexHeader')
        self.log.debug('Using header template from %s.' % templatePath)
        indexPath = os.path.join(logDir, 'index.html')
        shutil.copyfile(templatePath, indexPath)
        logFiles = [f for f in os.listdir(logDir)
                      if os.path.isfile(os.path.join(logDir, f))
                           and f.startswith(file_prefix+"_")
                           and f.endswith("."+file_suffix)]
        logFiles.sort(reverse=True)
        logURL = self.registryValue("logURL")
        if logURL != '': logURL = logURL + '/'
        # Separate logs by month, but only if the filename date format is what we expect
        filename_timeformat = self.registryValue('filenameTimestamp', channel)
        simple_split_months = False
        lastmonth = ''
        if filename_timeformat == "%Y-%m-%d":
            simple_split_months = True
        footerString = self.getFooter('indexFooter')
        with open(indexPath, encoding='utf-8', mode='a'+bin_mode) as indexFile:
            indexFile.write("<h2>Daily Logs for %s</h2>\n" %(channel))
            for f in logFiles:
                datename = f[len(file_prefix)+len(self.channel2URL(channel))+2
                             :-(len(file_suffix)+1)]
                if simple_split_months and datename[0:7] != lastmonth:
                    monthstring = datename[0:7]
                    if lastmonth == '': # First time through
                        indexFile.write('<h3>%s</h3>\n<ul>\n'%(monthstring))
                    else:
                        indexFile.write('</ul>\n<h3>%s</h3>\n<ul>\n'%(monthstring))
                    lastmonth = monthstring
                indexFile.write('\t<li><a href="%s%s">%s</a></li>\n'
                                %(logURL,f,datename))
            indexFile.write("</ul>\n")
            indexFile.write(footerString)

    def getFooter(self, templateName = 'footer'):
        ''' Reads the footer, and returns it as a string for appending to the
            log file.
        '''
        templatePath = self.getTemplatePath(templateName)
        self.log.debug('Using footer template from %s.' % templatePath)
        footerString = ''
        with open(templatePath, mode='r'+bin_mode) as footerFile:
            footerString = footerFile.read()
        return footerString

    def endLog(self, log):
        self.log.debug('Closing log file.')
        footerString = self.getFooter()
        log.write(footerString)
        log.close()

    def flush(self):
        self.checkLogNames()
        for log in self._logs():
            try:
                log.flush()
            except ValueError as e:
                if e.args[0] != 'I/O operation on a closed file':
                    self.log.exception('Odd exception:')

    def logNameTimestamp(self, channel):
        format = self.registryValue('filenameTimestamp', channel)
        return time.strftime(format, time.gmtime())

    def getLogName(self, channel):
        if self.registryValue('rotateLogs', channel):
            return '%s_%s_%s.%s' % (file_prefix, self.channel2URL(channel),
                                    self.logNameTimestamp(channel), file_suffix)
        else:
            return '%s_%s.%s' % (file_prefix, self.channel2URL(channel), file_suffix)

    def getLogDir(self, irc, channel):
        logDir = conf.supybot.directories.log.dirize(self.name())
        if self.registryValue('networkDirectory'):
                logDir = os.path.join(logDir,  irc.network)
        logDir = os.path.join(logDir, channel)
        if not os.path.exists(logDir):
            os.makedirs(logDir)
        return logDir

    def checkLogNames(self):
        for (irc, logs) in list(self.logs.items()):
            for (channel, log) in list(logs.items()):
                if self.registryValue('rotateLogs', channel):
                    name = self.getLogName(channel)
                    if name != os.path.basename(log.name):
                        self.log.debug('Timestamp change. Close the log.')
                        self.endLog(log)
                        del logs[channel]

    def deleteOldLogs(self, irc, channel, number2keep):
        logDir = self.getLogDir(irc, channel)
        logFiles = [f for f in os.listdir(logDir)
                            if os.path.isfile(os.path.join(logDir, f))
                               and f.startswith(file_prefix+"_")
                               and f.endswith("."+file_suffix)]
        logFiles.sort(reverse=True)
        need2delete = logFiles[number2keep:]
        if len(need2delete) > 0:
            self.log.info('Cleaning logs in "%s".', logDir)
            self.log.info('Will keep %s logfiles.', number2keep)
            for f in need2delete:
                self.log.info('Deleting old logfile "%s."', f)
                os.remove(os.path.join(logDir, f))

    def getLog(self, irc, channel):
        self.checkLogNames()
        try:
            logs = self.logs[irc]
        except KeyError:
            logs = ircutils.IrcDict()
            self.logs[irc] = logs
        if channel in logs:
            return logs[channel]
        else:
            try:
                name = self.getLogName(channel)
                logDir = self.getLogDir(irc, channel)
                logPath = os.path.join(logDir, name)
                if not os.path.isfile(logPath):
                    self.startLog(logPath, channel)
                    # Clean up old log files
                    number2keep = self.registryValue('deleteOldLogs', channel)
                    if number2keep > 0:
                        self.deleteOldLogs(irc, channel, number2keep)
                    # Generate a new index file
                    self.generateIndex(logDir, channel)
                else: # Remove the footer if it is there
                    # This will not work with huge log files
                    with open(logPath, mode='r'+bin_mode) as logFile:
                        logFileString = logFile.read()
                    footerString = self.getFooter()
                    if logFileString.endswith(footerString):
                        with open(logPath, mode='w'+bin_mode) as logFile:
                            logFile.write(logFileString[:-len(footerString)])
                log = open(logPath, mode='a'+bin_mode)
                logs[channel] = log
                return log
            except IOError:
                self.log.exception('Error opening log:')
                return FakeLog()

    def timestamp(self, log):
        format = conf.supybot.log.timestampFormat()
        if format:
            log.write(time.strftime(format, time.gmtime()))
            log.write('  ')

    def normalizeChannel(self, irc, channel):
        return ircutils.toLower(channel)

    def linkify(self, message):
        '''Enclose all URLs in the message with an href.'''
        return url_regex.sub(r'\1<a href="\2">\2</a>\3', message)

    def doLog(self, irc, channel, notice, nick, s, *args):
        ''' notice: Boolean. True if message should be styled as a notice. '''
        if not self.registryValue('enable', channel):
            return
        s = format(s, *args)
        channel = self.normalizeChannel(irc, channel)
        log = self.getLog(irc, channel)
        row_classes = row_class
        if notice:
            row_classes = row_class + " " + notice_class
        log.write('<p class="%s">' % row_classes)
        if self.registryValue('timestamp', channel):
            log.write('<span class="%s">' % timestamp_class)
            self.timestamp(log)
            log.write('</span>')
        if nick != None:
            log.write('<span class="%s">' % nick_class)
            log.write(html_escape("<%s> " %nick))
            log.write('</span>')
        if self.registryValue('stripFormatting', channel):
            s = ircutils.stripFormatting(s)
        log.write('<span class="%s">' % message_class)
        log.write(self.linkify(html_escape(s)))
        log.write('</span>')
        log.write('</p>\n')
        if self.registryValue('flushImmediately'):
            log.flush()

    @internationalizeDocstring
    def flushlog(self, irc, msg, args, channel):
        """ Optionally provide a channel, otherwise defaults to the current channel
        
        Make certain the latest information is saved to the filesystem.
        """
        if not channel:
            irc.reply("There is no default channel here, you can add a channel name to this command...")
            return
        if not self.registryValue('enable', channel):
            irc.reply("The channel [{0}] is not enabled, so no nead to flush your logs...".format(channel))
            return
        channel = self.normalizeChannel(irc, channel)
        log = self.getLog(irc, channel)
        log.flush()
        irc.reply("Woooosh, your log has been flushed...")
    flushlog = commands.wrap(flushlog, [commands.optional('channel')])


    def doPrivmsg(self, irc, msg):
        (recipients, text) = msg.args
        for channel in recipients.split(','):
            if irc.isChannel(channel):
                noLogPrefix = self.registryValue('noLogPrefix', channel)
                cap = ircdb.makeChannelCapability(channel, 'logChannelMessages')
                try:
                    logChannelMessages = ircdb.checkCapability(msg.prefix, cap,
                        ignoreOwner=True)
                except KeyError:
                    logChannelMessages = True
                nick = msg.nick or irc.nick
                if msg.tagged('HtmlLogger__relayed'):
                    (nick, text) = text.split(' ', 1)
                    nick = nick[1:-1]
                    msg.args = (recipients, text)
                if (noLogPrefix and text.startswith(noLogPrefix)) or \
                        not logChannelMessages:
                    text = '-= THIS MESSAGE NOT LOGGED =-'
                if ircmsgs.isAction(msg):
                    self.doLog(irc, channel, False, None,
                               '* %s %s', nick, ircmsgs.unAction(msg))
                else:
                    self.doLog(irc, channel, False, nick, '%s', text)

    def doNotice(self, irc, msg):
        (recipients, text) = msg.args
        for channel in recipients.split(','):
            if irc.isChannel(channel):
                self.doLog(irc, channel, True, None, '-%s- %s', msg.nick, text)

    def doNick(self, irc, msg):
        oldNick = msg.nick
        newNick = msg.args[0]
        for (channel, c) in irc.state.channels.items():
            if newNick in c.users:
                self.doLog(irc, channel, True, None,
                           '*** %s is now known as %s', oldNick, newNick)
    def doJoin(self, irc, msg):
        for channel in msg.args[0].split(','):
            if(self.registryValue('showJoinParts', channel)):
                self.doLog(irc, channel, True, None,
                           '*** %s <%s> has joined %s',
                           msg.nick, msg.prefix, channel)

    def doKick(self, irc, msg):
        if len(msg.args) == 3:
            (channel, target, kickmsg) = msg.args
        else:
            (channel, target) = msg.args
            kickmsg = ''
        if kickmsg:
            self.doLog(irc, channel, True, None,
                       '*** %s was kicked by %s (%s)',
                       target, msg.nick, kickmsg)
        else:
            self.doLog(irc, channel, True, None,
                       '*** %s was kicked by %s', target, msg.nick)

    def doPart(self, irc, msg):
        if len(msg.args) > 1:
            reason = " (%s)" % msg.args[1]
        else:
            reason = ""
        for channel in msg.args[0].split(','):
            if(self.registryValue('showJoinParts', channel)):
                self.doLog(irc, channel, True, None,
                           '*** %s <%s> has left %s%s',
                           msg.nick, msg.prefix, channel, reason)

    def doMode(self, irc, msg):
        channel = msg.args[0]
        if irc.isChannel(channel) and msg.args[1:]:
            self.doLog(irc, channel, True, None,
                       '*** %s sets mode: %s %s',
                       msg.nick or msg.prefix, msg.args[1],
                        ' '.join(msg.args[2:]))

    def doTopic(self, irc, msg):
        if len(msg.args) == 1:
            return # It's an empty TOPIC just to get the current topic.
        channel = msg.args[0]
        self.doLog(irc, channel, True, None,
                   '*** %s changes topic to "%s"', msg.nick, msg.args[1])

    def doQuit(self, irc, msg):
        if len(msg.args) == 1:
            reason = " (%s)" % msg.args[0]
        else:
            reason = ""
        if not isinstance(irc, irclib.Irc):
            irc = irc.getRealIrc()
        for (channel, chan) in self.lastStates[irc].channels.items():
            if(self.registryValue('showJoinParts', channel)):
                if msg.nick in chan.users:
                    self.doLog(irc, channel, True, None,
                               '*** %s <%s> has quit IRC%s',
                               msg.nick, msg.prefix, reason)

    def outFilter(self, irc, msg):
        # Gotta catch my own messages *somehow* :)
        # Let's try this little trick...
        if msg.command in ('PRIVMSG', 'NOTICE'):
            # Other messages should be sent back to us.
            m = ircmsgs.IrcMsg(msg=msg, prefix=irc.prefix)
            if msg.tagged('relayedMsg'):
                m.tag('HtmlLogger__relayed')
            self(irc, m)
        return msg


Class = HtmlLogger
# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
