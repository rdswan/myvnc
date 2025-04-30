#!/bin/bash
cd "$(dirname "$0")"

# Generate private key
openssl genrsa -out key.pem 2048

# Generate CSR with config file
openssl req -new -key key.pem -out cert.csr -config openssl.cnf

# Generate self-signed certificate with extensions
openssl x509 -req -days 365 -in cert.csr -signkey key.pem -out cert.pem \
    -extensions v3_req -extfile openssl.cnf

# Create template for CA chain bundle
cat > ca-chain.pem << 'EOF'
# CA Chain Bundle File
# 
# This file should contain the intermediate certificate chain for your SSL certificate.
# Replace this template content with your actual intermediate certificates.
#
# The certificates should be in PEM format, concatenated in the correct order,
# typically starting from the intermediate certificate closest to your server certificate
# and ending with the intermediate certificate closest to the root CA.
#
# Example structure:
# 
# -----BEGIN CERTIFICATE-----
# [Intermediate Certificate 1]
# -----END CERTIFICATE-----
# -----BEGIN CERTIFICATE-----
# [Intermediate Certificate 2]
# -----END CERTIFICATE-----
#
# Note: Do not include your server certificate or the root CA certificate in this file.
#       The server certificate should be in cert.pem and the private key in key.pem.
EOF

# Show certificate info
echo "Certificate generated with the following information:"
openssl x509 -in cert.pem -text -noout | grep "Subject:"
openssl x509 -in cert.pem -text -noout | grep "X509v3 Subject Alternative Name"
openssl x509 -in cert.pem -text -noout | grep "DNS:"

# Clean up
rm cert.csr

echo "Certificate generation complete!"
echo "A template for the CA chain bundle has been created at ca-chain.pem"
echo "Replace its contents with your actual intermediate certificates if needed." 