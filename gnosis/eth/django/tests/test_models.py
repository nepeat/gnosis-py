from django.core.exceptions import ValidationError
from django.db import transaction
from django.test import TestCase

from eth_account import Account
from ethereum.utils import check_checksum, sha3
from faker import Faker
from hexbytes import HexBytes

from ...constants import NULL_ADDRESS, SENTINEL_ADDRESS
from .models import EthereumAddress, EthereumAddressV2, Sha3Hash, Uint256

faker = Faker()


class TestModels(TestCase):
    def test_ethereum_address_field(self):
        for EthereumAddressModel in (EthereumAddress, EthereumAddressV2):
            with self.subTest(EthereumAddressModel=EthereumAddressModel):
                address = Account.create().address
                self.assertTrue(check_checksum(address))
                ethereum_address = EthereumAddressModel.objects.create(value=address)
                ethereum_address.refresh_from_db()
                self.assertTrue(check_checksum(ethereum_address.value))
                self.assertEqual(address, ethereum_address.value)

                EthereumAddressModel.objects.create(value=None)
                self.assertIsNone(EthereumAddressModel.objects.get(value=None).value)

                # Test special addresses
                for special_address in (NULL_ADDRESS, SENTINEL_ADDRESS):
                    EthereumAddressModel.objects.create(value=special_address)
                    self.assertIsNotNone(
                        EthereumAddressModel.objects.get(value=special_address)
                    )

                with self.assertRaisesMessage(
                    ValidationError,
                    '"0x23" value must be an EIP55 checksummed address.',
                ):
                    with transaction.atomic():
                        EthereumAddressModel.objects.create(value="0x23")

    def test_uint256_field(self):
        for value in [
            2,
            -2,
            2 ** 256,
            2 ** 260,
            25572735541615049941137326092682691158109824779649981270427004917341670006487,
            None,
        ]:
            uint256 = Uint256.objects.create(value=value)
            uint256.refresh_from_db()
            self.assertEqual(uint256.value, value)

        # Overflow
        with self.assertRaises(Exception):
            value = 2 ** 263
            Uint256.objects.create(value=value)

    def test_sha3_hash_field(self):
        value: bytes = sha3(faker.name())
        value_hex_without_0x: str = value.hex()
        value_hex_with_0x: str = "0x" + value_hex_without_0x
        value_hexbytes: HexBytes = HexBytes(value_hex_with_0x)

        values = [value, value_hex_without_0x, value_hex_with_0x, value_hexbytes]

        for v in values:
            sha3_hash = Sha3Hash.objects.create(value=v)
            sha3_hash.refresh_from_db()
            self.assertEqual(sha3_hash.value, value_hex_with_0x)

        for v in values:
            self.assertEqual(Sha3Hash.objects.filter(value=v).count(), len(values))

        # Hash null
        sha3_hash = Sha3Hash.objects.create(value=None)
        sha3_hash.refresh_from_db()
        self.assertIsNone(sha3_hash.value)

        # Hash too big
        value_hex_invalid: str = "0x" + value_hex_without_0x + "a"
        with self.assertRaises(Exception):
            Sha3Hash.objects.create(value=value_hex_invalid)
