import shelless, openSSHConfig
import os
from twisted.python.filepath import FilePath
from twisted.trial import unittest
from twisted.internet import reactor, defer, protocol
from twisted.cred import portal, credentials, checkers
from zope import interface
from twisted.conch.manhole_ssh import ConchFactory

# comments tagged with *8.2* means that this is meant to get around a bug in
# trial, and hopefully that bug will be fixed by 8.2

def execCommand(process, command):
    args = command.split()
    # *8.2*
    # reactor.spawnProcess(process, args[0], args, os.environ)
    reactor.callLater(0, 
                      reactor.spawnProcess, 
                      process, args[0], args, os.environ)
    return process.deferred


class TesterError(Exception):
    def __init__(self, value, data=None, exitCode=-1):
        Exception.__init__(self, value, data)
        self.value = value
        self.data = data
        self.exitCode = exitCode


class AlwaysAllow:
    credentialInterfaces = ( credentials.IUsernamePassword, 
                             credentials.ISSHPrivateKey )
    interface.implements(checkers.ICredentialsChecker)

    def requestAvatarId(self, credentials):
        return defer.succeed(credentials.username)


class SSHTester(protocol.ProcessProtocol):

    def __init__(self):
        self.data = ""
        self.error = ""
        self.deferred = defer.Deferred()
        self.connected = False
        self.queue = []

    def connectionMade(self):
        self.connected = True
        for item in self.queue:
            if item is None:
                self.finish()
            else:
                self.write(item)

    def write(self, data):
        if not self.connected:
            self.queue.append(data)
            return self.deferred
        
        self.data = ""
        self.error = ""
        self.transport.write(data)

    def finish(self):
        if not self.connected:
            self.queue.append(None)
        else:
            self.transport.closeStdin()

    def outReceived(self, data):
        self.data += data

    def errReceived(self, data):
        self.error += data

    def processEnded(self, reason):
        self.error = "\n".join(
            [ x for x in self.error.split("\n") 
              if not x.startswith("Connecting to")])
        if reason.value.exitCode != 0:
            self.deferred.errback(
                TesterError(self.error, self.data, reason.value.exitCode))
        else:
            self.deferred.callback(self.data)


class TestTester(unittest.TestCase):
    """
    Make sure I actually know what I'm doing here - test against a regular
    SSH server.
    """

    def setUp(self):
        f = FilePath(self.mktemp())
        f.createDirectory()
        self.serverOptions, self.clientOptions = openSSHConfig.setupConfig(
            f.path, 2222)

        class MyPP(protocol.ProcessProtocol):
            def __init__(self):
                self.readyDeferred = defer.Deferred()
                self.deferred = defer.Deferred()
            def processEnded(self, reason):
                self.deferred.callback("None")
            def errReceived(self, data): #because openSSH prints on stderr
                if "Server listening" in data:
                    self.readyDeferred.callback("Ready")

        self.pp = MyPP()
        self.server = execCommand(self.pp, 
                                  "/usr/sbin/sshd %s" % self.serverOptions)
        self.ssht = SSHTester()
    
    def tearDown(self):
        return self.pp.deferred

    def test_regSSH(self):
        self.pp.readyDeferred.addCallback(
            lambda x: execCommand(self.ssht, 
                                  'ssh %s echo Hello' % self.clientOptions))
        self.ssht.deferred.addCallback(self.assertEqual, "Hello\n")
        return self.ssht.deferred

    def test_regSFTP(self):
        self.pp.readyDeferred.addCallback(
            lambda x: execCommand(self.ssht, "sftp %s" % self.clientOptions))
        self.ssht.write('exit\n')
        self.ssht.finish()
        return self.ssht.deferred


class TestSecured:

    def realmFactory(self):
        raise NotImplementedError

    def setUp(self):
        """
        Starts a shelless SSH server.  Subclasses need to specify
        realmFactory
        """
        p = portal.Portal(self.realmFactory())
        p.registerChecker(AlwaysAllow())
        f = ConchFactory(p)
        #self.server = reactor.listenTCP(0, f)
        #self.port = self.server.getHost().port
        self.port = 2222
        self.server = reactor.listenTCP(self.port, f)
        self.ssht = SSHTester()

    def tearDown(self):
        return defer.maybeDeferred(self.server.stopListening)


class TestShelllessSSH(TestSecured, unittest.TestCase):

    def __init__(self, *args, **kwargs):
        unittest.TestCase.__init__(self, *args, **kwargs)
        
    def realmFactory(self):
        return shelless.ShelllessSSHRealm()

    def _checkFailure(self, failure):
        error = failure.value
        expected = 'does not provide shells or allow command execution'
        self.assertTrue(expected in error.value or expected in error.data)
        raise TesterError("ok!") 
        # stupid hack to insure that failure condition raised

    def test_noshell(self):
        d = execCommand(self.ssht, "ssh -p %d localhost" % self.port)
        d.addErrback(self._checkFailure)
        self.assertFailure(d, TesterError)
        return d

    def test_noexec(self):
        d = execCommand(self.ssht, 
                        'ssh -p %d localhost "ls"' % self.port)
        d.addErrback(self._checkFailure)
        self.assertFailure(d, TesterError)
        return d
