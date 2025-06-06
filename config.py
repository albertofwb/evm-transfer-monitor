CORE_RPC_URL = "https://rpc.coredao.org"
BSC_RPC_URL = "https://bsc-dataseed.binance.org/"


ConfigMap = {
    "core": {
        "rpc_url": CORE_RPC_URL,
        "scan_url": "https://scan.coredao.org",
        "token_name": "CORE",
    },
    "bsc": {
        "rpc_url": BSC_RPC_URL,
        "scan_url": "https://bscscan.com",
        "token_name": "BNB",
    }
}

ActiveChains = "bsc"
ActiveConfig = ConfigMap[ActiveChains]