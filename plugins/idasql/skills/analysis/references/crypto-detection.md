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
SELECT DISTINCT (SELECT name FROM funcs WHERE dc.func_addr >= address AND dc.func_addr < end_ea LIMIT 1) as func_name, dc.callee_name
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
SELECT printf('0x%X', address) as aes_sbox
FROM byte_search
WHERE pattern = '63 7C 77 7B F2 6B 6F C5'
ORDER BY address
LIMIT 1;

-- RSA public exponent (65537 = 0x10001)
SELECT printf('0x%X', address) as rsa_exponent
FROM byte_search
WHERE pattern = '01 00 01 00'
ORDER BY address
LIMIT 1;

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
SELECT (SELECT name FROM funcs WHERE func_addr >= address AND func_addr < end_ea LIMIT 1) as function, detail, source
FROM (SELECT * FROM crypto_imports UNION ALL SELECT * FROM crypto_strings)
ORDER BY function;
```
