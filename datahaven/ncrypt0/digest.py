import hashlib

class DigestError(Exception):
    def __init__( self, *args ) :
        Exception.__init__( self, *args )

class DigestType :
    def __init__( self, evpMd ) :
        self.m = hashlib.new(evpMd.lower())

    def name(self) :
        return self.m.name

    def size(self) :
        return self.m.digest_size

    def blockSize(self) :
        return self.m.block_size

class Digest:
    def __init__(self, digestType) :
        self.hash = digestType.m
        self.finalized = False

    def update(self, data) :
        if self.finalized:
            raise DigestError, 'digest operation is already completed'
        return self.hash.update(data)

    def digest(self, data=None) :
        if self.finalized:
            raise DigestError, 'digest operation is already completed'
        if data is not None :
            self.hash.update(data)   
        result = self.hash.digest()
        self.finalized = True      
        return result
