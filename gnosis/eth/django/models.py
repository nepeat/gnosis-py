import binascii
from typing import Optional, Union

from django.core import exceptions
from django.db import models
from django.utils.translation import gettext_lazy as _

from eth_typing import ChecksumAddress
from eth_utils import to_checksum_address
from hexbytes import HexBytes

from .validators import validate_checksumed_address

try:
    from django.db import DefaultConnectionProxy

    connection = DefaultConnectionProxy()
except ImportError:
    from django.db import connections

    connection = connections["default"]


class EthereumAddressField(models.CharField):
    default_validators = [validate_checksumed_address]
    description = "Ethereum address (EIP55)"
    default_error_messages = {
        "invalid": _('"%(value)s" value must be an EIP55 checksummed address.'),
    }

    def __init__(self, *args, **kwargs):
        kwargs["max_length"] = 42
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        del kwargs["max_length"]
        return name, path, args, kwargs

    def from_db_value(self, value, expression, connection):
        return self.to_python(value)

    def to_python(self, value):
        value = super().to_python(value)
        if value:
            try:
                return to_checksum_address(value)
            except ValueError:
                raise exceptions.ValidationError(
                    self.error_messages["invalid"],
                    code="invalid",
                    params={"value": value},
                )
        else:
            return value

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        return self.to_python(value)


class EthereumAddressV2Field(models.BinaryField):
    default_validators = [validate_checksumed_address]
    description = "Ethereum address (EIP55)"
    default_error_messages = {
        "invalid": _('"%(value)s" value must be an EIP55 checksummed address.'),
    }

    def __init__(self, *args, **kwargs):
        kwargs["max_length"] = 20
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        del kwargs["max_length"]
        return name, path, args, kwargs

    def from_db_value(
        self, value: memoryview, expression, connection
    ) -> Optional[ChecksumAddress]:
        if value:
            return to_checksum_address(value.hex())

    def get_prep_value(self, value: ChecksumAddress) -> Optional[bytes]:
        if value:
            return HexBytes(self.to_python(value))

    def to_python(self, value) -> Optional[ChecksumAddress]:
        if value is not None:
            try:
                return to_checksum_address(value)
            except ValueError:
                raise exceptions.ValidationError(
                    self.error_messages["invalid"],
                    code="invalid",
                    params={"value": value},
                )


class Uint256Field(models.DecimalField):
    description = _("Ethereum uint256 number")
    """
    Field to store ethereum uint256 values. Uses Decimal db type without decimals to store
    in the database, but retrieve as `int` instead of `Decimal` (https://docs.python.org/3/library/decimal.html)
    """

    def __init__(self, *args, **kwargs):
        kwargs["max_digits"] = 79  # 2 ** 256 is 78 digits
        kwargs["decimal_places"] = 0
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        del kwargs["max_digits"]
        del kwargs["decimal_places"]
        return name, path, args, kwargs

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        return int(value)


class HexField(models.CharField):
    """
    Field to store hex values (without 0x). Returns hex with 0x prefix.

    On Database side a CharField is used.
    """

    description = "Stores a hex value into an CharField"

    def from_db_value(self, value, expression, connection):
        return self.to_python(value)

    def to_python(self, value):
        return value if value is None else HexBytes(value).hex()

    def get_prep_value(self, value):
        if value is None:
            return value
        elif isinstance(value, HexBytes):
            return value.hex()[
                2:
            ]  # HexBytes.hex() retrieves hexadecimal with '0x', remove it
        elif isinstance(value, bytes):
            return value.hex()  # bytes.hex() retrieves hexadecimal without '0x'
        else:  # str
            return HexBytes(value).hex()[2:]

    def formfield(self, **kwargs):
        # We need max_lenght + 2 on forms because of `0x`
        defaults = {"max_length": self.max_length + 2}
        # TODO: Handle multiple backends with different feature flags.
        if self.null and not connection.features.interprets_empty_strings_as_nulls:
            defaults["empty_value"] = None
        defaults.update(kwargs)
        return super().formfield(**defaults)

    def clean(self, value, model_instance):
        value = self.to_python(value)
        self.validate(value, model_instance)
        # Validation didn't work because of `0x`
        self.run_validators(value[2:])
        return value


class Sha3HashField(HexField):
    def __init__(self, *args, **kwargs):
        kwargs["max_length"] = 64
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        del kwargs["max_length"]
        return name, path, args, kwargs


class Keccak256Field(models.BinaryField):
    description = "Keccak256 hash stored as binary"
    default_error_messages = {
        "invalid": _('"%(value)s" hash must be a 32 bytes hexadecimal.'),
        "length": _('"%(value)s" hash must have exactly 32 bytes.'),
    }

    def __init__(self, *args, **kwargs):
        kwargs["max_length"] = 32
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        del kwargs["max_length"]
        return name, path, args, kwargs

    def to_bytes(self, value) -> Optional[bytes]:
        if value is None:
            return
        else:
            try:
                result = HexBytes(value)
                if len(result) != 32:
                    raise exceptions.ValidationError(
                        self.error_messages["length"],
                        code="length",
                        params={"value": value},
                    )
                return result
            except (ValueError, binascii.Error):
                raise exceptions.ValidationError(
                    self.error_messages["invalid"],
                    code="invalid",
                    params={"value": value},
                )

    def from_db_value(
        self, value: memoryview, expression, connection
    ) -> Optional[bytes]:
        if value:
            return HexBytes(value.tobytes()).hex()

    def get_prep_value(self, value: Union[bytes, str]) -> Optional[bytes]:
        if value:
            return self.to_bytes(value)

    def to_python(self, value) -> Optional[str]:
        if value is not None:
            try:
                return self.to_bytes(value)
            except (ValueError, binascii.Error):
                raise exceptions.ValidationError(
                    self.error_messages["invalid"],
                    code="invalid",
                    params={"value": value},
                )
