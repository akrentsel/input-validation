def iperf_client_successful(msg:str) -> bool:
    return "connect failed" not in msg