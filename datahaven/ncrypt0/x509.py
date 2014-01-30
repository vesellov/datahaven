from OpenSSL.crypto import X509, X509Req, load_privatekey, load_certificate, FILETYPE_PEM, FILETYPE_ASN1, dump_certificate, dump_privatekey
    
cspace_ca_cert = """-----BEGIN CERTIFICATE-----
MIIC6DCCAdCgAwIBAwIBATANBgkqhkiG9w0BAQUFADAUMRIwEAYDVQQDEwljYS5j
c3BhY2UwHhcNMTMwNjIyMTc1NzI5WhcNMTMwNjIzMTc1NzI5WjAUMRIwEAYDVQQD
EwljYS5jc3BhY2UwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQDQjduL
0z8R7sOSsgg9RPjVB/mNUeZueSzmvk573oH0TOROAU5bCLz9KRPTfMcb7RfT7Z4i
WAe1PZ4owV9qxG2aKYAQc/eMjz28Fj4EDri+eqaBBWgLFU2cuQ1wwgJN2Cr+oekg
oEb7qRRbT74oKJ6tEnTGpzteCzRGg3UOfOdjaZCbr0Mny7Ke70kBbbAiX4irPoNp
d2d9cEcUR0Hf9FNRTOOov65yv0cKoJgd45wb/GzNLEXWr6djwX4ii9IjpD5dcWIf
Cp1heLF4y0c1xJrlwmSnP3wVdAkXugNwu6jswz38Zhb3hyjrp0ehB43Cidy6kEW7
4IQolQF73mbWfVidAgMBAAGjRTBDMBIGA1UdEwEB/wQIMAYBAf8CAQAwDgYDVR0P
AQH/BAQDAgEGMB0GA1UdDgQWBBT6qS+mNKpPJIHr5ECMt6/2YLDyWDANBgkqhkiG
9w0BAQUFAAOCAQEA0ERNkCD8+zEp9kGJXlx+LAA8RVkROjyHG5MAAFV2C3QXofBz
j5nyAqJRDeUfYlWNxaOt9U9B4fgC/FBEuxK1B8oRDkBAquM7Eyb/gccF6MET7com
NZtWgiv8YLyUav1aJaZ1WTHpIKlpLK5zNKf/2FA7hbknlZ7NFAYDshkzhIz9Zw7W
l53Hd3LxdsW5G4MNUeCdU1OFk2TujQA9irIT7rGziyS0RWgu8Hbu4lznfI08eYt7
+6THbRfHg30TelKggvnRupQ9z8HgvyKluCoYCCbd8QA2gembd/gzLelhC364U6Li
ivR0rU61uOXZjnvv23MxHrEwODTJuO+Ch+nCZg==
-----END CERTIFICATE-----"""
    
cspace_ca_key = """-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEA0I3bi9M/Ee7DkrIIPUT41Qf5jVHmbnks5r5Oe96B9EzkTgFO
Wwi8/SkT03zHG+0X0+2eIlgHtT2eKMFfasRtmimAEHP3jI89vBY+BA64vnqmgQVo
CxVNnLkNcMICTdgq/qHpIKBG+6kUW0++KCierRJ0xqc7Xgs0RoN1DnznY2mQm69D
J8uynu9JAW2wIl+Iqz6DaXdnfXBHFEdB3/RTUUzjqL+ucr9HCqCYHeOcG/xszSxF
1q+nY8F+IovSI6Q+XXFiHwqdYXixeMtHNcSa5cJkpz98FXQJF7oDcLuo7MM9/GYW
94co66dHoQeNwoncupBFu+CEKJUBe95m1n1YnQIDAQABAoIBAFD7RIz+8jacaATG
bLyd06Gk/xoI+1laZD0VGJSwyfV7BgvkJfDja79B/BjbEtWdMutwET90v0l5K7jX
nZ1vuL9r7fZ1kWJbHLW0TVB2Bvav2Yev+b6T/xckJDvsmchwcAGADW5FzkpaVTU/
ua8OVs8No5qfxUW3RA09bm65wX+wAdbBFNmwU8lV5rLUjiKVIFyxmvQ5o822b8cp
iU1BEgVMSTsmpB/R3535kcrag40Pa93MX5Cc7rh2opPPUgh2xGfqD/IaVoguZzPA
j+l0ltduPwGs2AsET8YLY+XEcCNURl1taoQNNVpL2l9G6U0pG+AZ4e7GBjOhhng0
LZho7gECgYEA/nkQTUM4ux/BDH1ZbuP90cZqD1p9Kd5+6j53nssgNGEZOw9mxAJg
b3W2LgURa7bxOVOhlb0PZvja3MLgGn1hpIt9o8ZfxLELlSi/pHaCHCFojdKNo13V
YhiPtJ8BX14o34DG9uzrNxQln5SCedYuatwetfKi6FmadQ12gy9g080CgYEA0c5A
M6wGzL8QIyh2bZh766tEuTX2idcDajf7FyR/dyiNpcm3PjtbELj1M2hzZvaEjWWA
F2Ir98W03U4bhdX5uCxstADX08EySZmaxNlzQwMSjTHE0nD/MpoiPZXZStjW86vz
YtLCo/G66OHvJEy+0xLwDWfITWgM4Fot4wsUaBECgYEAwFy50v3+s410fEGBSo80
PtBTOln4BZ94pxAjkrkQFihUT038LC1zwq3j0nPoUFmRjflHS48IRpnVsE3r5Hpl
RmJfzl7V5DTFgbK089jVz/f9NkA064qyFB5m+227NuFR2mpZfS1pPVCQhEpaO0mJ
+yN8X6QUO7oIRXWw4cf91P0CgYEAtPSMYUTVVJDSTVCf3GTxNNGyY4BMlJSTiHCi
K1K6cb7TdROm7ZDqOWEdc2p6Zmrm5sGNmh19SKYIGfw9NtDYImaGlzZG8IeoZNyM
JY5boIes34T2en8lTLKuJ6nwEWM2+lHriOe5IwfiKux7gzaCO7EQxK8njsPYn0SI
YVP0FNECgYALs+i/Vx65sc+R3PIK2cF3WakhcPYhhvdW3M833Yk0jMvo6IvSvLm3
FIzP6vII70f1l5OE3D6EUVyYskBI+JB1aQiIaxbUGOv/jcjKmol61Uz3O6cEV8Ov
YVzUfRzAfp8hOP2k3X2xkZ5ewp/kZW3cNteg5m+BwAgv1z14BVJtdw==
-----END RSA PRIVATE KEY----- """
        
def makeX509CASignedCertifiacte(userName, keyID, rsaKey, ca_key_path='ca.key', ca_cert_path='ca.pem'):  
    # ca_cert = load_certificate(FILETYPE_PEM, ca_cert_path)
    # ca_key = load_privatekey(FILETYPE_PEM, ca_key_path) 
    fin = open(ca_cert_path, 'rb')
    ca_cert_src = fin.read()
    fin.close()
    fin = open(ca_key_path, 'rb')
    ca_key_src = fin.read()
    fin.close()
    ca_cert = load_certificate(FILETYPE_PEM, ca_cert_src)
    ca_key = load_privatekey(FILETYPE_PEM, ca_key_src)
    key = load_privatekey(FILETYPE_PEM, rsaKey.toPEM_PrivateKey())
    cert = X509()
    cert.get_subject().CN = userName + '@' + keyID
    cert.set_serial_number(1)
    cert.set_notBefore("20000101000000Z")
    cert.set_notAfter("22000101000000Z")
    cert.set_issuer(ca_cert.get_subject())
    cert.set_pubkey(key)
    cert.sign(ca_key, "sha1")    
    return cert
        
def makeX509Certificate(userName, rsaKey):
    key = load_privatekey(FILETYPE_PEM, rsaKey.toPEM_PrivateKey())
    cert = X509()
    cert.get_subject().CN = userName
    cert.set_issuer(cert.get_subject())
    cert.set_pubkey(key)
    cert.set_notBefore("20000101000000Z")
    cert.set_notAfter("22000101000000Z")
    cert.set_serial_number(1)
    cert.sign(key, "sha1")
    return cert

class X509Error(Exception):
    def __init__( self, *args ) :
        Exception.__init__( self, *args )

