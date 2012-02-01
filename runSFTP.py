import csftp

from twisted.conch.manhole_ssh import ConchFactory
from zope import interface
from twisted.internet import defer
from twisted.cred import credentials, checkers, portal
from twisted.internet import reactor

class AlwaysAllow(object):
    credentialInterfaces = credentials.IUsernamePassword,
    interface.implements(checkers.ICredentialsChecker)

    def requestAvatarId(self, credentials):
        return defer.succeed(credentials.username)


p = portal.Portal(csftp.ChrootedSSHRealm('.'))
p.registerChecker(AlwaysAllow())
reactor.listenTCP(2222, ConchFactory(p))
reactor.run()
