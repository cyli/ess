from csftp import shelless

import sys

from twisted.conch.ssh import transport, userauth, connection, channel, common
from twisted.conch.manhole_ssh import ConchFactory
from twisted.internet import defer
from twisted.cred import credentials, checkers, portal
from twisted.internet import protocol, reactor
from twisted.python import log

from zope import interface


class ClientTransport(transport.SSHClientTransport):

    def verifyHostKey(self, pubKey, fingerprint):
        return defer.succeed(1)


    def connectionSecure(self):
        self.requestService(ClientUserAuth('cyli', ClientConnection()))



class ClientUserAuth(userauth.SSHUserAuthClient):

    def getPassword(self, prompt=None):
        return  defer.succeed("")  # return blank password

#    def getPublicKey(self):
#        return keys.getPublicKeyString(data=pu)  #set pu when testing client

#    def getPrivateKey(self):
#        return defer.succeed(keys.getPrivateKeyObject(data=pr))
#        #  set pr when testing client



class ClientConnection(connection.SSHConnection):

    def serviceStarted(self):
        self.openChannel(CatChannel(conn=self))



class CatChannel(channel.SSHChannel):

    name = 'session'

    def channelOpen(self, data):
        self.catData = data
        self.conn.sendRequest(self, 'exec', common.NS('ls'), wantReply=1)


    def dataReceived(self, data):
        self.catData += data


    def closed(self):
        print 'We got this from "ls":', self.catData
        self.loseConnection()
        reactor.stop()



def testClient(host, port):
    protocol.ClientCreator(reactor, ClientTransport).connectTCP(host, port)
    log.startLogging(sys.stdout)
    reactor.run()



class AlwaysAllow:
    credentialInterfaces = credentials.IUsernamePassword,
    interface.implements(checkers.ICredentialsChecker)

    def requestAvatarId(self, credentials):
        return defer.succeed(credentials.username)

log.startLogging(sys.stdout)
p = portal.Portal(shelless.ShelllessSSHRealm())
p.registerChecker(AlwaysAllow())
reactor.listenTCP(2222, ConchFactory(p))
f = protocol.ClientFactory()
f.protocol = ClientTransport
reactor.connectTCP('localhost', 2222, f)
reactor.run()

#testClient('suijin', 22)
