def compute_bcc(data: bytes) -> int:
    """BCC校验: 对所有字节逐字节XOR"""
    result = 0
    for b in data:
        result ^= b
    return result
