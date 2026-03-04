# Crypto Detection Patterns

## OpenSSL

```sql
-- OpenSSL imports
SELECT name, module FROM imports
WHERE name LIKE '%SSL_%' OR name LIKE '%EVP_%' OR name LIKE '%BIO_%'
   OR name LIKE '%OPENSSL_%' OR name LIKE '%PEM_%'
ORDER BY module, name;

-- OpenSSL strings
SELECT content, printf('0x%X', address) as addr FROM strings
WHERE content LIKE '%openssl%' OR content LIKE '%libssl%'
   OR content LIKE '%libcrypto%' OR content LIKE '%-----BEGIN%';

-- Functions referencing OpenSSL
SELECT DISTINCT func_at(dc.func_addr) as func_name, dc.callee_name
FROM disasm_calls dc
JOIN imports i ON dc.callee_addr = i.address
WHERE i.name LIKE '%SSL_%' OR i.name LIKE '%EVP_%'
ORDER BY func_name;
```

## Windows CryptoAPI

```sql
-- CryptoAPI imports
SELECT name FROM imports
WHERE name LIKE '%Crypt%' OR name LIKE '%Cert%'
   OR name IN ('BCryptOpenAlgorithmProvider', 'BCryptGenerateSymmetricKey',
               'BCryptEncrypt', 'BCryptDecrypt', 'BCryptDestroyKey',
               'BCryptCloseAlgorithmProvider', 'BCryptHash')
ORDER BY name;

-- DPAPI usage (credential storage)
SELECT name FROM imports
WHERE name IN ('CryptProtectData', 'CryptUnprotectData',
               'CryptProtectMemory', 'CryptUnprotectMemory');
```

## AES/RSA/Hash Patterns

```sql
-- AES S-Box detection (common constant)
SELECT printf('0x%X', search_first('63 7C 77 7B F2 6B 6F C5')) as aes_sbox;

-- RSA public exponent (65537 = 0x10001)
SELECT printf('0x%X', search_first('01 00 01 00')) as rsa_exponent;

-- Algorithm strings
SELECT content, printf('0x%X', address) as addr FROM strings
WHERE content LIKE '%AES%' OR content LIKE '%RSA%' OR content LIKE '%SHA%'
   OR content LIKE '%MD5%' OR content LIKE '%HMAC%' OR content LIKE '%DES%'
   OR content LIKE '%Blowfish%' OR content LIKE '%ChaCha%';

-- Comprehensive crypto audit (CTE)
WITH crypto_imports AS (
    SELECT func_addr, callee_name as detail, 'import' as source
    FROM disasm_calls dc
    JOIN imports i ON dc.callee_addr = i.address
    WHERE i.name LIKE '%Crypt%' OR i.name LIKE '%SSL_%' OR i.name LIKE '%EVP_%'
       OR i.name LIKE '%BCrypt%' OR i.name LIKE '%Hash%'
),
crypto_strings AS (
    SELECT x.from_ea as func_addr, s.content as detail, 'string' as source
    FROM strings s
    JOIN xrefs x ON x.to_ea = s.address
    WHERE s.content LIKE '%AES%' OR s.content LIKE '%RSA%' OR s.content LIKE '%SHA%'
)
SELECT func_at(func_addr) as function, detail, source
FROM (SELECT * FROM crypto_imports UNION ALL SELECT * FROM crypto_strings)
ORDER BY function;
```
