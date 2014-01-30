#!/usr/bin/python
#transport_email.py
#
#
#    Copyright DataHaven.NET LTD. of Anguilla, 2006
#    Use of this software constitutes acceptance of the Terms of Use
#      http://datahaven.net/terms_of_use.html
#    All rights reserved.
#
#


import os
import sys
import smtplib
import re
import time
import tempfile
from StringIO import StringIO


##import email
import email.Encoders
import email.MIMEMultipart
import email.MIMEBase


try:
    from twisted.internet import reactor
except:
    sys.exit('Error initializing twisted.internet.reactor in transport_email.py')


import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
from twisted.mail.smtp import sendmail
from twisted.mail.smtp import SMTPSenderFactory
from twisted.mail.smtp import ESMTPSenderFactory
from twisted.mail.pop3 import AdvancedPOP3Client as POP3Client


from twisted.internet.defer import Deferred, succeed
from twisted.internet.protocol import ClientFactory
from twisted.internet.ssl import ClientContextFactory
from OpenSSL.SSL import SSLv3_METHOD


import misc
import dhnio
import settings
import transport_control
import tmpfile

#info: [email, server, port, username, password, ssl, need_auth]

##misc.DebugLevel = 14

log_state = False

#maximum length of any single line in the message
MAX_LINE_LENGTH = 1024

ready_receiving = True

#-------------------------------------------------------------------------------

PollingObject = None
class PollingControl:
    timemark = time.time()
    #LAST_ACTIVITY_PERIOD = 15.0*60.0   #last activity period. then increase polling time

    current_polling_interval = 30.0  # start off checking every minute
    SHORT_POLLING = 10.0   # if we had activity recently, check every 15 seconds
    MEDIUM_POLLING = 30.0  # after 1 minute of inactivity check every minute until 15 minutes
    LONG_POLLING = 90.0   # after 15 minutes of inactivity check every 15 minutes

    def init(self):
        self.clear()
        self.update()

    def clear(self):
        self.timemark = time.time()

    def deltatime(self):
        return time.time() - self.timemark

# we don't want to update the email timeout based on activity
#    def update_timeout(self):
#        if self.deltatime() < self.LAST_ACTIVITY_PERIOD:
#            misc.setEmailSendTimeout(settings.SendTimeOutEmail())
#        else:
#            misc.setEmailSendTimeout(settings.SendTimeOutEmail() * 10)
##        transport_control.log('email', 'use % timeout' % (str(misc.getEmailSendTimeout())))

#
#    def update_polltime(self):
#        if self.deltatime() < self.LAST_ACTIVITY_PERIOD:
#            misc.setEmailPollingTime(settings.EmailPollingTime())
#        else:
#            misc.setEmailPollingTime(settings.EmailPollingTime() * 10)
##        transport_control.log('email', 'use %s polling time' % (str(misc.getEmailPollingTime())))

    def update_polltime(self):
        if self.deltatime() > self.LONG_POLLING:
            self.current_polling_interval = self.LONG_POLLING
        elif self.deltatime() > self.MEDIUM_POLLING:
            self.current_polling_interval = self.MEDIUM_POLLING
        else:
            self.current_polling_interval = self.SHORT_POLLING

    def update(self):
        dhnio.Dprint(14, 'transport_email:PoolingControl.update: deltatime='+str(self.deltatime()))
        self.update_polltime()
        #self.update_timeout()

    def receive(self):
##        self.counter += 1.0
##        if self.counter > self.MAX_COUNTER:
        self.update()
        self.clear()

    def send(self):
        self.update()
        self.clear()


def check_info(info):
    if len(info) < 6:
        return False
    if info[0].strip() == '' or info[1].strip() == '':
        return False
    try:
        port_ = int(info[2])
    except:
        return False
    return True


def poll():
    global PollingObject
    if PollingObject is None:
        PollingObject = PollingControl()
    return PollingObject

def pollingInterval():
    return poll().current_polling_interval

#-------------------------------------------------------------------------------

##############################################################
## Sending ###################################################
##############################################################

def send_smtplib(host, login, password, ssl_flag, addr, to, subject, filename):
    dhnio.Dprint(14, 'transport_email.send_smtplib to: ' + str(to))

    fin = file(filename, 'rb')
    bin_data = fin.read()
    fin.close()



    msg = email.MIMEMultipart.MIMEMultipart()
    msg["Subject"] = subject
    msg["From"]    = addr
    msg["To"]      = to
    part = email.MIMEBase.MIMEBase('application', "octet-stream")
    part.set_payload( bin_data+'end' )
    email.Encoders.encode_base64(part)
    part.add_header('Content-Disposition', 'attachment; filename="%s"' % os.path.basename(filename))
    msg.attach(part)

    try:
        server = smtplib.SMTP(host)
    except:
##        transport_control.msg('e', 'could not conect to smtp server')
##        transport_control.connectionStatusCallback('email', to, None, 'could not conect to smtp server')
        transport_control.sendStatusReport(to, filename,
        'failed', 'email',
        None, 'could not conect to smtp server')
        return

    if dhnio.DebugLevel > 14:
        server.set_debuglevel(1)
    dhnio.Dprint(14, 'transport_email.send_smtplib: SSL FLAG:'+str(ssl))
    if ssl_flag:
        try:
            dhnio.Dprint(14, 'transport_email.send_smtplib ehlo')
            server.ehlo()
            dhnio.Dprint(14, 'transport_email.send_smtplib starttls')
            server.starttls()
            dhnio.Dprint(14, 'transport_email.send_smtplib ehlo')
            server.ehlo()
        except:
            dhnio.Dprint(14, 'transport_email.send_smtplib: No support ssl')
##            transport_control.connectionStatusCallback('email', to, None, 'server did not support ssl' )
            transport_control.sendStatusReport(to, filename,
            'failed', 'email',
            None, 'server did not support ssl')
##            transport_control.msg('e', 'server did not support ssl')

    try:
        dhnio.Dprint(14, 'transport_email.send_smtplib login')
        server.login(login, password)
    except:
        dhnio.Dprint(14, 'transport_email.send_smtplib: Not need to login')

    try:
        dhnio.Dprint(14, 'transport_email.send_smtplib: sendmail')
        server.sendmail(addr, [to], msg.as_string())
        dhnio.Dprint(14, 'transport_email.send_smtplib: close')
        server.close()
        dhnio.Dprint(14, 'transport_email.send_smtplib: done')
    except:
##        transport_control.connectionStatusCallback('email', to, None, 'unknown error during sending message')
        transport_control.sendStatusReport(to, filename,
        'failed', 'email',
        None, 'unknown error during sending message')
##        transport_control.msg('e', 'can not send message')

def sendTwistedMail(host, addr, to, subject, filename, port=25):
    dhnio.Dprint(14, 'transport_email.sendTwistedMail to: ' + str(to))

    fin = file(filename, 'rb')
    bin_data = fin.read()
    fin.close()

    msg = email.MIMEMultipart.MIMEMultipart()
    msg["Subject"] = subject
    msg["From"]    = addr
    msg["To"]      = to

    part = email.MIMEBase.MIMEBase('application', "octet-stream")
    part.set_payload( bin_data+'end' )
    email.Encoders.encode_base64(part)
    part.add_header('Content-Disposition', 'attachment; filename="%s"' % os.path.basename(filename))
    msg.attach(part)

    try:
        port_ = int(port)
    except:
        port_ = 25

    return sendmail(host, addr, [to], msg.as_string(), port=port_)

class MySenderFactory(ESMTPSenderFactory):
    pass
##    def buildProtocol(self, addr):
##        p = ESMTPSenderFactory.buildProtocol(self, addr)
##        dhnio.Dprint(6, 'transport_email.MyESMTPSenderFactory.buildProtocol obj=%s tls=%s' % (str(p), str(p.tlsMode)))
##        return p


def sendTwistedMailAuth(host, port, login, password, ssl_flag, need_login, addr, to, subject, filename):
    dhnio.Dprint(14, 'transport_email.sendTwistedMailAuth to:%s ssl:%s auth:%s ' % (str(to),str(ssl_flag), str(need_login)))

    fin = file(filename, 'rb')
    bin_data = fin.read()
    fin.close()

    msg = email.MIMEMultipart.MIMEMultipart()
    msg["Subject"] = subject
    msg["From"]    = addr
    msg["To"]      = to

    part = email.MIMEBase.MIMEBase('application', "octet-stream")
    part.set_payload( bin_data+'end' )
    email.Encoders.encode_base64(part)
    part.add_header('Content-Disposition', 'attachment; filename="%s"' % os.path.basename(filename))
    msg.attach(part)


    try:
        port_ = int(port)
    except:
        port_ = 25
    messageText = msg.as_string()
    cf = ClientContextFactory()
    cf.method = SSLv3_METHOD
    result = Deferred()
    factory = MySenderFactory(
        login,
        password,
        addr,
        to,
        StringIO(messageText),
        result,
        contextFactory=cf,
        requireTransportSecurity=ssl_flag,
        requireAuthentication=need_login,)
    if ssl_flag:
        conn = reactor.connectSSL(host, port_, factory, cf)
    else:
        conn = reactor.connectTCP(host, port_, factory)
    return result


def send(filename, email, subject = 'datahaven_transport', reactor_stop=False, use_smtplib=False):
    transport_control.log('email', 'start sending to ' + email)
    smtp_info = [
            settings.getEmailAddress(),   #0
            settings.getSMTPHost(),       #1
            settings.getSMTPPort(),       #2
            settings.getSMTPUser(),       #3
            settings.getSMTPPass(),       #4
            settings.getSMTPSSL(),        #5
            settings.getSMTPNeedLogin()]  #6

    if smtp_info[0].strip() == '' or smtp_info[1].strip() == '':
        dhnio.Dprint(1, 'transport_email.send empty mailbox info. check your email options')
##        transport_control.msg('e', 'empty mailbox info. check your email options')
##        transport_control.connectionStatusCallback('email', email, None, 'empty mailbox info. check your email options')
        transport_control.sendStatusReport(email, filename,
            'failed', 'email',
            None, 'empty mailbox info. check your email options')
        return

##    print smtp_info
##    smtp_info = smtp3_info
    if not os.path.isfile(filename):
        dhnio.Dprint(1, 'transport_email.send wrong file name: %s' % filename)
##        transport_control.msg('e', 'wrong file name %s' % filename)
        return
    from_address = smtp_info[0]
    dhnio.Dprint(8, 'transport_email.send  from:%s to:%s' % (from_address, email))

    if use_smtplib:
        #send via smtplib
        try:
            send_smtplib(
                smtp_info[1],
                smtp_info[3],
                smtp_info[4],
                smtp_info[5],
                from_address,
                email,
                subject,
                filename)
        except:
            dhnio.Dprint(1, 'transport_email.send NETERROR sending email ' + dhnio.formatExceptionInfo())
##            transport_control.msg('e', 'Error sending email')
            transport_control.log('email', 'error sending email')
##            transport_control.connectionStatusCallback('email', email, None, 'error sending email')
            transport_control.sendStatusReport(email, filename,
                'failed', 'email',
                None, 'error sending email')
            return
##        if misc.transport_control_using():
        transport_control.sendStatusReport(email, filename,
            'finished', 'email')  # only one outstanding send per host
        transport_control.log('email', 'done')
        poll().send()
    else:
        #Send via Twisted
        def ok(x):
            dhnio.Dprint(14, 'transport_email.send.ok: sending done')
##            if misc.transport_control_using():
            # only one outstanding send per host
            transport_control.sendStatusReport(email, filename,
                'finished', 'email')
            transport_control.log('email', 'message successful sent')
            poll().send()
            if reactor_stop:
                reactor.stop()
        def fail(x):
##            if misc.transport_control_using():
            dhnio.Dprint(1, 'transport_email.send.fail NETERROR sending email \n' + str(x.getErrorMessage()))
##            transport_control.msg('e', 'error sending email: '  + str(x.getErrorMessage()) )
##            transport_control.connectionStatusCallback('email', smtp_info[0], x, 'error sending email')
            transport_control.sendStatusReport(email, filename,
                'failed', 'email',
                x, 'error sending email')
            transport_control.log('email', 'error sending email'  + str(x.getErrorMessage()))
            if reactor_stop:
                reactor.stop()

        if smtp_info[6]:
            #1th method
            res = sendTwistedMailAuth(
                smtp_info[1],
                smtp_info[2],
                smtp_info[3],
                smtp_info[4],
                smtp_info[5],
                smtp_info[6],
                from_address,
                email,
                subject,
                filename)
        else:
            #2th method:
            res = sendTwistedMail(
                smtp_info[1],
                smtp_info[0],
                email,
                subject,
                filename,
                smtp_info[2])
        res.addCallback(ok)
        res.addErrback(fail)
        return res


def send_public(filename, email, subject = 'datahaven_transport', reactor_stop=False, use_smtplib=False):
    smtp_info = [
            settings.getEmailAddress(),   #0
            settings.getSMTPHost(),       #1
            settings.getSMTPPort(),       #2
            settings.getSMTPUser(),       #3
            settings.getSMTPPass(),       #4
            settings.getSMTPSSL(),        #5
            settings.getSMTPNeedLogin()]  #6
    def ok(x):
        dhnio.Dprint(14, 'transport_email.send_public.ok: sending done')
##        if misc.transport_control_using():
        transport_control.sendStatusReport(email, filename,
            'finished', 'email')  # only one outstanding send per host
        transport_control.log('email', 'message successful sent')
        poll().send()
        if reactor_stop:
            reactor.stop()
    def fail(x):
        dhnio.Dprint(1, 'transport_email.send_public.fail NETERROR sending email \n' + str(x.getErrorMessage()))
##        transport_control.msg('e', 'error sending email: ' + str(x.getErrorMessage()))
##        transport_control.connectionStatusCallback('email', smtp_info[0], x, 'error sending email')
        transport_control.sendStatusReport(email, filename,
            'failed', 'email',
            x, 'error sending email')
        transport_control.log('email', 'NETERROR sending email')
        if reactor_stop:
            reactor.stop()

    res = sendTwistedMailAuth(
        smtp_info[1],
        smtp_info[2],
        smtp_info[3],
        smtp_info[4],
        smtp_info[5],
        smtp_info[6],
        smtp_info[0],
        email,
        subject,
        filename)
    res.addCallback(ok)
    res.addErrback(fail)
    return res


##############################################################
## Recevie POP ###################################################
##############################################################


def errorHandler(err):
    dhnio.Dprint(1, 'transport_email.errorHandler NETERROR \n' + str(err))
##    reactor.stop()
##    print err
##    raise err

class MyPOP3Client(POP3Client):
    linesize = MAX_LINE_LENGTH
    current_filename = ''
    def lineReceived(self, line):
        dhnio.Dprint(19, 'transport_email.lineReceived')
        if log_state:
            print '>>>:', line
##            print len(line)
        if len(line) <= self.linesize:
##            while line != '':
##                buf = line[:self.linesize]
##                POP3Client.lineReceived(self, buf+'\r\n')
##                line = line[self.linesize:]
##        else:
            POP3Client.lineReceived(self, line)

    def sendLine(self, line):
        dhnio.Dprint(19, 'transport_email.sendLine')
        if log_state:
            print '<<<:', line
        if len(line) <= self.linesize:
            POP3Client.sendLine(self, line)

    def connectionMade(self):
        dhnio.Dprint(14, 'transport_email.connectionMade')
        self.allowInsecureLogin = True
        self.startedTLS = True
        self.do_login()

##    def connectionLost(self, reason):
##        dhnio.Dprint(12, 'transport_email.connectionLost' + str(reason))

    def do_login(self):
        dhnio.Dprint(14, 'transport_email.do_login')
        self.login(self.factory.login,self.factory.password).addCallbacks(
            self.check_mailbox, self.err_login)

    def err_login(self, err):
        dhnio.Dprint(6, 'transport_email.err_login NETERROR ' + str(err))
##        transport_control.msg('e', 'error login on email server: ' + str(err))
##        transport_control.connectionStatusCallback('email', self.transport.getPeer(), err, 'error login on the email server')
        transport_control.receiveStatusReport('', 'failed',
            'email', self.transport.getPeer(),
             err, 'error login on the email server')
        self.prepare_loop('err_login')

    def check_mailbox(self, ignore):
        dhnio.Dprint(8, 'transport_email.check_mailbox')
        self.do_stat()

    def do_stat(self):
        self.stat().addCallbacks(
            self.set_stats, self.err_stat)

    def err_stat(self, err):
        dhnio.Dprint(6, 'transport_email.err_stat NETERROR ' + str(err))
##        transport_control.msg('e', 'can not retreive list of messages')
##        transport_control.connectionStatusCallback('email', self.transport.getPeer(), err, 'can not retreive list of messages')
        transport_control.receiveStatusReport('', 'failed',
            'email', self.transport.getPeer(),
             err, 'can not retreive list of messages')
        self.finish()

    def set_stats(self, stats):
        dhnio.Dprint(16, 'transport_email.set_stats')
        self.num_messages = stats[0]
        self.cur_message = 0
        transport_control.log('email', 'checking mailbox')
        if self.num_messages == 0:
            self.no_messages()
        else:
            self.retrieve(0).addCallbacks(
                self.do_retrieve_msg, self.err_retrieve_msg)

    def do_retrieve_msg(self, lines):
##        dhnio.Dprint(12, 'transport_email.do_retrieve_msg')
        msg_src = "\r\n".join(lines)
        msg = email.message_from_string(msg_src)
        self.process_msg(msg)

    def err_retrieve_msg(self, err):
        dhnio.Dprint(6, 'transport_email.err_retrieve_msg '+str(err))
##        print err
##        transport_control.msg('e', 'error retreive message')
##        transport_control.connectionStatusCallback('email', self.transport.getPeer(), err, 'error retreive message')
        transport_control.receiveStatusReport('', 'failed',
            'email', self.transport.getPeer(),
             err, 'error retreive message')
        self.finish()
##        raise err

    def process_msg(self, msg):
        dhnio.Dprint(12, 'transport_email.process_msg')
        take = False
        if msg['Subject'] == 'datahaven_transport':
            take = True
#            fout, self.current_filename = tempfile.mkstemp(".dhn-email-in")
            fout, self.current_filename = tmpfile.make("email-in")
            dhnio.Dprint(8, 'transport_email.message from: ' + str(msg['From']))
            transport_control.log('email', 'receiving file from ' + str(msg['From']))
            for part in msg.walk():
                if part.get_content_maintype() == 'multipart':
                    continue
                src = part.get_payload(decode=True)
                src = src[:-3]
                if src != None:
                    os.write(fout,src)
            os.close(fout)
##            transport_control.log('email', 'download... ')
            poll().receive()


        if take:
            self.delete(self.cur_message).addCallbacks(
                self.delete_msg, self.err_delete_msg)
        else:
            self.cur_message += 1
            if self.cur_message < self.num_messages:
                self.retrieve(self.cur_message).addCallbacks(
                    self.do_retrieve_msg, self.err_retrieve_msg)
            else:
                self.no_messages()

    def delete_msg(self, ignore):
        global ready_receiving
        dhnio.Dprint(14, 'transport_email.delete_msg')
        self.cur_message += 1
        if self.cur_message < self.num_messages:
            self.retrieve(self.cur_message).addCallbacks(
                self.do_retrieve_msg, self.err_retrieve_msg)
        else:
            self.no_messages()

        dhnio.Dprint(14, 'transport_email: received file ' + self.current_filename)
        if self.factory.receive_event is not None:
            self.factory.receive_event(self.current_filename)

        transport_control.log('email', 'receiving done. remove message from server')
##        if misc.transport_control_using() and ready_receiving:
        if ready_receiving:
            transport_control.receiveStatusReport(self.current_filename, "finished",
            'email', self.transport.getPeer())

    def err_delete_msg(self, err):
        dhnio.Dprint(6, 'transport_email.err_delete_msg NETERROR')
##        transport_control.msg('e', 'can not delete message from the server')
##        transport_control.connectionStatusCallback('email', self.transport.getPeer(), err, 'can not delete message from the server')
        transport_control.receiveStatusReport('', 'failed',
            'email', self.transport.getPeer(),
             err, 'can not delete message from the server')
        self.prepare_loop()
##        raise err

    def no_messages(self):
        global ready_receiving
        dhnio.Dprint(16, 'transport_email.no_messages')
        if not ready_receiving:
            dhnio.Dprint(8, 'transport_email.no_messages: mailbox is empty')
            transport_control.log('email', 'MAILBOX IS EMPTY. ready to receive new messages')
            ready_receiving = True
##        if self.factory.no_messages_event is not None:
##            self.factory.no_messages_event()
        self.finish()

    def finish(self):
        dhnio.Dprint(16, 'transport_email.finish')
        self.quit().addCallbacks(
            self.do_logout, self.err_logout)

    def do_logout(self, ignore):
        dhnio.Dprint(14, 'transport_email.do_logout')
###        timeout = misc.getEmailPollingTime()
##        timeout = pollingInterval()
##        transport_control.log('email', 'logout. polling time is: ' + str(timeout))
##        dhnio.Dprint(14, 'transport_email.do_logout. polling time is: ' + str(timeout))
##        timeout = self.factory.timeout
##        timeout = misc.ReceiveTimeOutEmail()
##        transport_control.log('email', 'current traffic: ' + str(poll().traffic()))
##        delaycall = reactor.callLater(timeout, self.factory.loop_callback)
        delaycall = self.prepare_loop()
        if self.factory.finish_event is not None:
            self.factory.finish_event(delaycall)
        self.transport.loseConnection()

    def prepare_loop(self, status=''):
        timeout = pollingInterval()
        if status == 'err_login':
            timeout *= 20
        dhnio.Dprint(10, 'transport_email.prepare_loop timeout=' + str(timeout))
        delaycall = reactor.callLater(timeout, self.factory.loop_callback)
        return delaycall

    def err_logout(self, err):
        dhnio.Dprint(6, 'transport_email.err_logout NETERROR' + str(err))
##        transport_control.msg('e', 'error logout from the server')
##        transport_control.connectionStatusCallback('email', self.transport.getPeer(), err, 'error logout from the server')
        transport_control.receiveStatusReport('', 'failed',
            'email', self.transport.getPeer(),
             err, 'error logout from the server')
        self.prepare_loop()
##        raise err

class PopChecker(ClientFactory):
    protocol = MyPOP3Client
    def __init__(self,
            login, password,
            timeout, loop_callback,
            receive_event=None,
            finish_event=None,
            no_messages_event=None):
        dhnio.Dprint(14, 'transport_email.PopChecker.__init__')
        self.login = login
        self.password = password
        self.timeout = timeout
        self.loop_callback = loop_callback
        self.receive_event = receive_event
        self.finish_event = finish_event

##    def clientConnectionLost(self, connector, reason):
##        dhnio.Dprint(12, 'transport_email.PopChecker.clientConnectionLost')
##        def reconnect():
##            connector.connect()
##
##    def clientConnectionFailed(self, connector, reason):
##        dhnio.Dprint(12, 'transport_email.PopChecker.clientConnectionFailed')

##def _loop():
##    dhnio.Dprint(12, 'transport_email._loop')
##    c = PopChecker(pop_login, pop_password, pop_timeout, _loop)
##    reactor.connectTCP(pop_server, pop_port, c)

class PopCheckerServer(Deferred):
    def __init__(self, server, port, login, password,
            ssl_flag, timeout=5,
            receive_event=None, no_messages_event=None):
        Deferred.__init__(self)
        dhnio.Dprint(16, 'transport_email.PopCheckerServer.__init__')
        self.server = server
        try:
            self.port = int(port)
        except:
            self.port = 110
        self.ssl_flag = ssl_flag
        self.addCallbacks(self.stop,self.fail)
        self.loopcall = None
        self.shutdown = False
        self.checker = PopChecker(login, password,
            timeout, self.run, receive_event,
            finish_event=self.finish_callback,
            no_messages_event=no_messages_event)

    def finish_callback(self, delaycall):
        dhnio.Dprint(14, 'transport_email.PopCheckerServer.finish_callback ' + str(delaycall))
        self.loopcall = delaycall

    def run(self):
        dhnio.Dprint(14, 'transport_email.PopCheckerServer.run')
        poll().update()
##        poll().clear()
        if self.shutdown:
            dhnio.Dprint(14, 'transport_email.PopCheckerServer.run - NEED SHUTDOWN')
            return
        if self.ssl_flag == 'True':
            self.runner = reactor.connectSSL(self.server, int(self.port), self.checker, ClientContextFactory())
            dhnio.Dprint(14, 'transport_email.connectSSL: %s: %s'% (self.server, str(self.port)))
        else:
            self.runner = reactor.connectTCP(self.server, int(self.port), self.checker)
            dhnio.Dprint(14, 'transport_email.connectTCP: %s: %s'% (self.server, str(self.port)))

    def stop(self, a):
        dhnio.Dprint(14, 'transport_email.PopCheckerServer.stop')
        self.stopListening()

    def fail(self, a):
        dhnio.Dprint(14, 'transport_email.PopCheckerServer.fail')
        self.stopListening()

    def stopListening(self):
        dhnio.Dprint(14, 'transport_email.PopCheckerServer.stopListening')
##        try:
##        print dir(self.checker.protocol) #.exit()
##        print self.checker.protocol.stop_me
##        print self.loopcall
        if self.loopcall is not None:
            try:
                self.loopcall.cancel()
            except:
                dhnio.Dprint(14, 'transport_email.PopCheckerServer.stopListening - loop call already canceled')
##        print self.runner
        self.runner.disconnect()

        return succeed(1)
##            self.checker.stopFactory()
##        except:
##            dhnio.Dprint(6, "errro. i can't disconnect")

#email_info = [email, pop3_server, port, login, password]
def receive(email_info, timeout=15, receive_event=None):
    transport_control.log('email', 'start receiving from '+str(email_info[0]))
    dhnio.Dprint(8, 'transport_email.receive. start looking at [%s:%s]  user: %s' % (email_info[1], email_info[2], email_info[3]))
##    print email_info
    server = PopCheckerServer(email_info[1], email_info[2], email_info[3], email_info[4], email_info[5], timeout, receive_event)
    server.loopcall = reactor.callLater(0, server.run)
    return server


##############################################################
### INIT #####################################################
##############################################################

def init():
    dhnio.Dprint(4, 'transport_email.init')
    global ready_receiving
    ready_receiving = False
    poll().init()

##    email_info = [
##            settings.getEmailAddress(),
##            settings.getPOPHost(),
##            settings.getPOPPort(),
##            settings.getPOPUser(),
##            settings.getPOPPass(),
##            settings.getPOPSSL()]
##
##    transport_control.log('email', 'cleaning email account...')
##    dhnio.Dprint(5, 'transport_email.init. start reading at [%s:%s]  user: %s' % (email_info[1], email_info[2], email_info[3]))
####    print email_info
##    mylistener = None
##    def no_messages():
##        transport_control.log('email','cleaning done')
##        mylistener.stopListening()
##    mylistener = PopCheckerServer(
##        email_info[1],
##        email_info[2],
##        email_info[3],
##        email_info[4],
##        email_info[5],
##        20,
##        no_messages_event=no_messages)
##    mylistener.loopcall = reactor.callLater(0, mylistener.run)


##############################################################
### private tests ############################################
##############################################################

##def my_tests():
####    _loop()
####    send('send-webdav.py',to_address)
##    send('misc.pyc',to_address)
####    reactor.run()
##
####my_tests()
##
##if __name__ == '__main__':
##    main()
##    reactor.run()
##

#-------------------------------------------------------------------------------

def mytest():
    dhnio.SetDebug(30)

##    filename = "identity.pyc"              # just some file to send

    pop_info = [
        settings.getEmailAddress(),
        settings.getPOPHost(),
        settings.getPOPPort(),
        settings.getPOPUser(),
        settings.getPOPPass(),
        settings.getPOPSSL()]

    smtp_info = [
        settings.getEmailAddress(),
        settings.getSMTPHost(),
        settings.getSMTPPort(),
        settings.getSMTPUser(),
        settings.getSMTPPass(),
        settings.getSMTPSSL()]



##    smtp_info = smtp2_info


    if len(sys.argv) == 1:
        print pop_info
        if not check_info(pop_info):
            print 'need POP info. see user configuration file'
            sys.exit()
        mylistener = None
        def receive_file(x):
            print 'receive 1 file.', x
##            mylistener.stopListening()
        mylistener = receive(pop_info, receive_event=receive_file)
##        reactor.run()
    elif len(sys.argv) == 3:
##        send(filename, pop_info[0])
        send(sys.argv[2], sys.argv[1], reactor_stop=True, use_smtplib=False)
    elif len(sys.argv) == 4 and sys.argv[1].lower() == '-p':
        send_public(sys.argv[3], sys.argv[2], reactor_stop=True, use_smtplib=False)
    else:
        print 'usage:'
        print 'to receive:   transport_email'
        print 'to send   :   transport_email [e-mail] [filename]'
        print 'to send from public datahaven server:'
        print '              transport_email -p [e-mail] [filename]'
        sys.exit(0)


if __name__ == "__main__":
    init()
    mytest()

##    keys = sys.modules.keys()
##    keys.sort()
##    for k in keys:
##        print str(k) + ' ' + str(sys.modules[k]) + '\n\n'

    reactor.run()


