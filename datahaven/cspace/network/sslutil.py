import time
from ncrypt0.x509 import makeX509Certificate, makeX509CASignedCertifiacte, cspace_ca_cert
from ncrypt0.ssl import SSLContext, SSL_METHOD_TLSv1, SSL_VERIFY_MODE_NONE, SSL_VERIFY_MODE_SELF_SIGNED

#------------------------------------------------------------------------------ 

CONTEXT_FOR_CLIENT = 1
CONTEXT_FOR_SERVER = 2

_CA_KEY_PATH = 'ca.key'
_CA_CERT_PATH = 'ca.pem'

#------------------------------------------------------------------------------ 

def set_CA_key_path(pth):
    global _CA_KEY_PATH
    _CA_KEY_PATH = pth
    
def set_CA_cert_path(pth):
    global _CA_CERT_PATH
    _CA_CERT_PATH = pth

#------------------------------------------------------------------------------ 

def makeClientSSLContext( userName, keyID, rsaKey, verify_callback=None) :
    return makeSSLContext(userName, keyID, rsaKey, verify_callback, CONTEXT_FOR_CLIENT)

def makeServerSSLContext( userName, keyID, rsaKey, verify_callback=None) :
    return makeSSLContext(userName, keyID, rsaKey, verify_callback, CONTEXT_FOR_SERVER)

#------------------------------------------------------------------------------ 

def makeSSLContext( userName, keyID, rsaKey, verify_callback=None, clientORserver=None) :
    # cert = makeX509Certificate(userName, rsaKey)
    global _CA_KEY_PATH
    global _CA_CERT_PATH
    cert = makeX509CASignedCertifiacte(userName, keyID, rsaKey, _CA_KEY_PATH, _CA_CERT_PATH)
    sslContext = SSLContext( SSL_METHOD_TLSv1 )
    if clientORserver == CONTEXT_FOR_CLIENT:
        sslContext.setPrivateKey( rsaKey )
        sslContext.setCertificate( cert )
        sslContext.checkPrivateKey()
        sslContext.setVerifyMode( SSL_VERIFY_MODE_SELF_SIGNED, verify_callback )
        sslContext.loadVerifyLocations(_CA_CERT_PATH)
    elif clientORserver == CONTEXT_FOR_SERVER:
        sslContext.setPrivateKey( rsaKey )
        sslContext.setCertificate( cert )
        sslContext.checkPrivateKey()
        sslContext.setVerifyMode( SSL_VERIFY_MODE_SELF_SIGNED, verify_callback )
        sslContext.loadVerifyLocations(_CA_CERT_PATH)
    else:
        sslContext.setPrivateKey( rsaKey )
        sslContext.setCertificate( cert )
        sslContext.checkPrivateKey()
        sslContext.setVerifyMode( SSL_VERIFY_MODE_NONE, verify_callback )
    return sslContext

