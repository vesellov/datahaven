import os
import binascii
#import warnings
#from Crypto.pct_warnings import PowmInsecureWarning
#warnings.filterwarnings("ignore", category=PowmInsecureWarning)
from Crypto.PublicKey import RSA
from asn1 import DerSequence
from OpenSSL.crypto import load_privatekey, dump_privatekey, FILETYPE_PEM, FILETYPE_ASN1
from pyasn1.codec.der import encoder as der_encoder
from pyasn1.codec.der import decoder as der_decoder
from base64 import b64decode, b64encode
from twisted.conch.ssh import keys
from hexcode import hexDecode, hexEncode

PADDING_PKCS1 = 0
PADDING_PKCS1_OAEP = 1

class RSAError(Exception):
    def __init__( self, *args ) :
        Exception.__init__( self, *args )

class RSAKey:
    def __init__(self):
        self.key = None
        
    def fromPEM_PublicKey(self, publicKeyData):
        try:
            key64 = ''
            for line in publicKeyData.splitlines():
                if line.count('BEGIN RSA PUBLIC KEY') or line.count('END RSA PUBLIC KEY'):
                    continue
                key64 += line.strip()
            pubSeq = DerSequence()
            pubSeq.decode(b64decode(key64))
            self.key = RSA.construct( (pubSeq[0], pubSeq[1]) )
        except:
            raise RSAError, 'unable to load object from data'            
        
    def toPEM_PublicKey(self):
        pemSeq = DerSequence()
        pemSeq[:] = [ self.key.key.n, self.key.key.e ]
        s = b64encode(pemSeq.encode())
        src = '-----BEGIN RSA PUBLIC KEY-----\n'
        while True:
            src += s[:64] + '\n'
            s = s[64:]
            if s == '':
                break
        src += '-----END RSA PUBLIC KEY-----'
        return src

    def fromPEM_PrivateKey(self, privKeyData, passphrase=None):
        try:
            self.key = keys.Key.fromString(privKeyData, passphrase=passphrase, type='private_openssh').keyObject
        except:
            raise RSAError, 'unable to load object from data'

    def toPEM_PrivateKey(self, passphrase=None):
        binaryKey = self.toDER_PrivateKey()
        chunks = [ binascii.b2a_base64(binaryKey[i:i+48]) for i in range(0, len(binaryKey), 48) ]
        pem = "-----BEGIN RSA PRIVATE KEY-----\n"
        pem += ''.join(chunks)
        pem += "-----END RSA PRIVATE KEY-----"
        k = keys.Key.fromString(pem, type='private_openssh')
        return k.toString('openssh', passphrase).strip()

    def fromDER_PublicKey(self, publicKeyData):
        d = der_decoder.decode(publicKeyData)
        self.key = RSA.construct((long(d[0][0]), long(d[0][1])))
        
    def toDER_PublicKey(self):
        derPK = DerSequence()
        derPK[:] = [ self.key.key.n, self.key.key.e ]
        return derPK.encode()
    
    def fromDER_PrivateKey(self, privateKeyData):
        try:
            d = der_decoder.decode(privateKeyData)
            self.key = RSA.construct((long(d[0][1]),
                                      long(d[0][2]),
                                      long(d[0][3]),
                                      long(d[0][5]),
                                      long(d[0][4]),
                                      long(d[0][8]),))
        except:
            raise RSAError, 'unable to load object from data'            
        
    def toDER_PrivateKey(self):
        derPrivKey = DerSequence()
        derPrivKey[:] = [ 0, 
                          self.key.n, 
                          self.key.e, 
                          self.key.d, 
                          self.key.q, 
                          self.key.p,
                          self.key.d % (self.key.q-1),
                          self.key.d % (self.key.p-1), 
                          self.key.u ]
        return derPrivKey.encode()
        
    def fromPKey_PublicKey(self, pkey):
        src = dump_privatekey(FILETYPE_ASN1, pkey)
        pub_der = DerSequence()
        pub_der.decode(src)
        self.key = RSA.construct((long(pub_der._seq[1]), long(pub_der._seq[2])))
    
    def construct(self, tup):
        self.key = RSA.construct(tup)
    
    def generate(self, bits=1024):
        try:
            self.key = RSA.generate(bits, os.urandom)
        except:
            raise RSAError, 'key generation failed'

    def size(self):
        return self.key.size()
    
    def check(self):
        return True
    
    def getN(self) :
        return self.key.key.n

    def getE(self) :
        return self.key.key.e

    def getD(self) :
        return self.key.key.d

    def getP(self) :
        return self.key.key.p

    def getQ(self) :
        return self.key.key.q
    
    def hasPublicKey(self) :
        return True

    def hasPrivateKey(self):
        return self.key.has_private()
    
    def getPublicKey(self) :
        return (self.key.key.n, self.key.key.e)
    
    def getPrivateKey(self):
        return  ( self.key.key.n, 
                  self.key.key.e, 
                  self.key.key.d, 
                  self.key.key.p,
                  self.key.key.q, 
                  self.key.key.d % (self.key.key.p-1),
                  self.key.key.d % (self.key.key.q-1),
                  self.key.key.u ) 
        
    def paddingSize(self, paddingMode):
        if paddingMode == 0:
            return 12
        if paddingMode == 1:
            return 42
        raise RSAError, 'unknown padding mode'
    
    def maxInputSize(self, paddingMode=1):
        return self.size() - self.paddingSize(paddingMode)
    
    def encrypt(self, data, paddingMode=1):
        try:
            return self.key.encrypt(data)
        except:
            raise RSAError, 'RSA encryption failed'
    
    def decrypt(self, data, paddingMode=1):
        try:
            return self.key.decrypt(data)
        except:
            raise RSAError, 'RSA decryption failed'
    
    def sign(self, digest, digestType):
        try:
            return self.key.sign(digest, digestType)
        except:
            raise RSAError, 'RSA sign failed'

    def verify(self, signature, digest, digestType):
        try:
            return self.key.verify(digest, (long(signature),))
        except:
            raise RSAError, 'RSA verify failed'


