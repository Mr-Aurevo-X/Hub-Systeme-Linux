# SPDX-License-Identifier: GPL-3.0-or-later
"""On-chain donation addresses — local display / copy only (no network)."""

from __future__ import annotations

from typing import NamedTuple


class CryptoWallet(NamedTuple):
    symbol: str
    name: str
    address: str


CRYPTO_WALLETS: tuple[CryptoWallet, ...] = (
    CryptoWallet("BTC", "Bitcoin", "bc1ql2wj4spehf2zu40329lspr9a3thzuy9gyy4xm7"),
    CryptoWallet("ETH", "Ethereum", "0x21daa0434976FDA8C4Ce6fA494602e734f051e21"),
    CryptoWallet("HYPE", "Hyperliquid (EVM)", "0x21daa0434976FDA8C4Ce6fA494602e734f051e21"),
    CryptoWallet("SOL", "Solana", "E1MoayFrzC6Phe4g17Qfswub8hk1ytnp8Db8qguqPdv1"),
    CryptoWallet("USDT", "Tron (TRC-20)", "TKVvKinR4Ksrs2f8AN5NuVeysmizmh42Ch"),
    CryptoWallet("USDC", "Solana", "E1MoayFrzC6Phe4g17Qfswub8hk1ytnp8Db8qguqPdv1"),
    CryptoWallet("BCH", "Bitcoin Cash", "bitcoincash:qrdwzcg372fvahkk0rz7y8mrr0fnaw2ygg5fk6mfke"),
    CryptoWallet("LTC", "Litecoin", "ltc1qmnm2j2nn59ycnhk3x0t33c24fpxlxjxrxha2mj"),
    CryptoWallet("DOGE", "Dogecoin", "D7649yHmrYMCGcfFfoKVxyAAot45HCmAVp"),
    CryptoWallet("XRP", "XRP Ledger", "rEtVrJSb3BTANFKT2aTCS9jUahp74v3U6K"),
    CryptoWallet("XLM", "Stellar", "GDISSPFVTPNKMVMX5OSNJBLS2DYBMP4ZTBPRSORHWXI4NJHFS5KKSBRN"),
)
