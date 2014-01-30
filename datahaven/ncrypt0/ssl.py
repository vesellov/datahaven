from OpenSSL import SSL
from OpenSSL.crypto import load_privatekey, load_certificate
from OpenSSL.crypto import FILETYPE_ASN1, FILETYPE_PEM
#from OpenSSL.SSL import SSLv2_METHOD, SSLv3_METHOD, SSLv23_METHOD, TLSv1_METHOD
#from OpenSSL.SSL import VERIFY_PEER, VERIFY_FAIL_IF_NO_PEER_CERT, VERIFY_CLIENT_ONCE, VERIFY_NONE
from OpenSSL.SSL import OP_NO_SSLv2 , OP_NO_SSLv3 , OP_SINGLE_DH_USE

SSL_METHOD_SSLv2 = 0
SSL_METHOD_SSLv3 = 1
SSL_METHOD_TLSv1 = 2
SSL_METHOD_SSLv23 = 3
SSL_METHOD_MAX = 4

SSL_METHOD_TYPE_CLIENT = 0
SSL_METHOD_TYPE_SERVER = 1
SSL_METHOD_TYPE_GENERIC = 2
SSL_METHOD_TYPE_MAX = 3

SSL_VERIFY_MODE_NONE = 0
SSL_VERIFY_MODE_SELF_SIGNED = 1
SSL_VERIFY_MODE_MAX = 2

SSL_OP_NO_SSLv2 = SSL.OP_NO_SSLv2
SSL_OP_NO_SSLv3 = SSL.OP_NO_SSLv3
SSL_OP_SINGLE_DH_USE = SSL.OP_SINGLE_DH_USE

class SSLError(Exception):
    def __init__( self, *args ) :
        Exception.__init__( self, *args )

class SSLWantError( SSLError ): 
    pass

class SSLWantReadError( SSLWantError ):
    pass

class SSLWantWriteError( SSLWantError ):
    pass

class SSLWantX509LookupError( SSLWantError ):
    pass

class SSLContext():
    def __init__( self, sslMethod ) :
        m = {SSL_METHOD_SSLv2: SSL.SSLv2_METHOD,
             SSL_METHOD_SSLv3: SSL.SSLv3_METHOD,
             SSL_METHOD_TLSv1: SSL.TLSv1_METHOD,
             SSL_METHOD_SSLv23: SSL.SSLv23_METHOD,}.get(sslMethod, SSL.TLSv1_METHOD)
        self.c = SSL.Context(m)
        self.verifyCallback = None
        
    def setCertificate(self, cert) :
        self.c.use_certificate(cert)
        
    def setPrivateKey(self, rsakey) :
        self.c.use_privatekey(load_privatekey(FILETYPE_ASN1, rsakey.toDER_PrivateKey()))
        
    def checkPrivateKey(self):
        self.c.check_privatekey()
        
    def setVerifyMode(self, m, callback=None):
        cb = self.selfSignedVerifyCallback
        if callback is not None:
            cb = callback
        if m == SSL_VERIFY_MODE_NONE:
            self.c.set_verify(SSL.VERIFY_NONE, cb)
        elif m == SSL_VERIFY_MODE_SELF_SIGNED:
            self.c.set_verify(SSL.VERIFY_PEER|SSL.VERIFY_FAIL_IF_NO_PEER_CERT, cb)
    
    def setOptions(self, flags):
        return self.c.set_options(flags)
    
    def selfSignedVerifyCallback(self, conn, cert, errno, depth, preverify_ok):
        return preverify_ok
    
    def loadVerifyLocations(self, path):
        self.c.load_verify_locations(path)
    
    
class SSLConnection():
    def __init__( self, sslContext, sock ) :
        self.conn = SSL.Connection(sslContext.c, sock)
        self.sock = sock
        
    def setConnectState(self):
        self.conn.set_connect_state()
        
    def setAcceptState(self):
        self.conn.set_accept_state()
        
    def connect(self):
        try:
            self.conn.do_handshake()
        except SSL.WantReadError:
            raise SSLWantReadError
        except SSL.WantWriteError:
            raise SSLWantWriteError
        except SSL.WantX509LookupError:
            raise SSLWantX509LookupError
        except SSL.Error, e:
            raise SSLError, e
        except:
            raise

    def accept(self):
        try:
            self.conn.do_handshake()
        except SSL.WantReadError:
            raise SSLWantReadError
        except SSL.WantWriteError:
            raise SSLWantWriteError
        except SSL.WantX509LookupError:
            raise SSLWantX509LookupError
        except SSL.Error, e:
            raise SSLError, e
        except:
            raise
        
    def getPeerCertificate(self):
        return  self.conn.get_peer_certificate()
    
    def pending(self):
        return self.conn.pending()
    
    def recv(self, bufsize):
        try:
            return self.conn.recv(bufsize)
        except SSL.WantReadError:           
            raise SSLWantReadError
        except SSL.WantWriteError:          
            raise SSLWantWriteError
        except SSL.WantX509LookupError:     
            raise SSLWantX509LookupError
        except SSL.Error, e:                   
            raise SSLError, e 
        except:                             
            raise
    
    def send(self, data):
        try:
            return self.conn.send(data)    
        except SSL.WantReadError:
            raise SSLWantReadError
        except SSL.WantWriteError:
            raise SSLWantWriteError
        except SSL.WantX509LookupError:
            raise SSLWantX509LookupError
        except SSL.Error, e:
            raise SSLError, e  
        except:
            raise

    def shutdown(self):
        self.sock = None
        try:
            return self.conn.shutdown()
        except SSL.WantReadError:
            raise SSLWantReadError
        except SSL.WantWriteError:
            raise SSLWantWriteError
        except SSL.WantX509LookupError:
            raise SSLWantX509LookupError
        except SSL.Error, e:
            raise SSLError, e 
        except:
            raise

