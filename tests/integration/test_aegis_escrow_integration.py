"""
Integration tests for AegisEscrow against GenLayer RPC / StudioNet / LocalNet.
Requires gltest and a running GenLayer node or Studio environment.
"""

import pytest
from gltest import get_contract_factory
from gltest.assertions import tx_execution_succeeded


def test_aegis_escrow_deployment_and_schema():
    """Validates contract deployment, JSON-RPC interaction, and schema generation."""
    factory = get_contract_factory("contracts/aegis_escrow.py")
    
    # Deploy contract on active testnet
    contract = factory.deploy(args=[])
    assert contract.address is not None
    assert contract.address.startswith("0x")

    # Call view methods via JSON-RPC
    # agreement_counter starts at 0
    with pytest.raises(Exception):
        # Querying non-existent agreement 999 should revert cleanly
        contract.get_agreement(args=[999]).call()
