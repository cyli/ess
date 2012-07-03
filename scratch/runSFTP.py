from twisted.conch.manhole_ssh import ConchFactory
from twisted.cred import credentials, checkers, portal
from twisted.internet import defer, reactor
from twisted.python.log import startLogging

from zope import interface

from ess import essftp


class AlwaysAllow(object):
    credentialInterfaces = credentials.IUsernamePassword,
    interface.implements(checkers.ICredentialsChecker)

    def requestAvatarId(self, credentials):
        return defer.succeed(credentials.username)


p = portal.Portal(essftp.EssFTPRealm('TEMP/ROOT'))
p.registerChecker(AlwaysAllow())
reactor.listenTCP(2222, ConchFactory(p))
startLogging(open('log.txt', 'w+'))
reactor.run()
