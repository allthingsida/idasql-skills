# Network Detection Patterns

## Socket API (Berkeley/Winsock)

```sql
-- Socket imports
SELECT name, module FROM imports
WHERE name IN ('socket', 'connect', 'bind', 'listen', 'accept',
               'send', 'recv', 'sendto', 'recvfrom', 'select',
               'closesocket', 'shutdown', 'getaddrinfo', 'freeaddrinfo',
               'gethostbyname', 'inet_addr', 'inet_ntoa',
               'htons', 'htonl', 'ntohs', 'ntohl')
ORDER BY name;

-- Winsock initialization
SELECT name FROM imports
WHERE name IN ('WSAStartup', 'WSACleanup', 'WSAGetLastError',
               'WSASocketW', 'WSAConnect', 'WSASend', 'WSARecv');

-- Functions using sockets
SELECT DISTINCT func_at(dc.func_addr) as func_name
FROM disasm_calls dc
JOIN imports i ON dc.callee_addr = i.address
WHERE i.name IN ('socket', 'connect', 'send', 'recv', 'bind', 'listen', 'accept')
ORDER BY func_name;
```

## curl / libcurl

```sql
-- curl imports
SELECT name, module FROM imports
WHERE name LIKE 'curl_%'
ORDER BY name;

-- curl strings
SELECT content, printf('0x%X', address) as addr FROM strings
WHERE content LIKE '%curl%' OR content LIKE '%libcurl%'
   OR content LIKE '%CURLOPT%';

-- URL strings
SELECT content, printf('0x%X', address) as addr FROM strings
WHERE content LIKE 'http://%' OR content LIKE 'https://%'
   OR content LIKE 'ftp://%' OR content LIKE 'ws://%';
```

## WinHTTP / WinINet

```sql
-- WinHTTP imports
SELECT name FROM imports
WHERE name LIKE 'WinHttp%'
ORDER BY name;

-- WinINet imports
SELECT name FROM imports
WHERE name LIKE 'Internet%' OR name LIKE 'Http%' OR name LIKE 'Ftp%'
ORDER BY name;

-- Comprehensive network audit (CTE)
WITH net_imports AS (
    SELECT func_addr, callee_name as api, 'import' as source
    FROM disasm_calls dc
    JOIN imports i ON dc.callee_addr = i.address
    WHERE i.name IN ('socket', 'connect', 'send', 'recv', 'WSAStartup')
       OR i.name LIKE 'WinHttp%' OR i.name LIKE 'Internet%'
       OR i.name LIKE 'curl_%'
),
net_strings AS (
    SELECT x.from_ea as func_addr, s.content as api, 'string' as source
    FROM strings s
    JOIN xrefs x ON x.to_ea = s.address
    WHERE s.content LIKE 'http://%' OR s.content LIKE 'https://%'
       OR s.content LIKE '%User-Agent%' OR s.content LIKE '%Content-Type%'
)
SELECT func_at(func_addr) as function, api, source
FROM (SELECT * FROM net_imports UNION ALL SELECT * FROM net_strings)
ORDER BY function;
```
