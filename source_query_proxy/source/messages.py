# Copyright (C) 2013 Oliver Ainsworth

import collections
import functools
import socket
import struct

from . import util

NO_SPLIT = -1
SPLIT = -2

_missing = object()


class BrokenMessageError(Exception):
    pass


class BufferExhaustedError(BrokenMessageError):
    def __init__(self, message='Incomplete message'):
        BrokenMessageError.__init__(self, message)


class SkipEncodeError(Exception):
    pass


def on_broken_default(func):
    @functools.wraps(func)
    def wrap(*args, **kw):
        default = kw.pop('default', _missing)

        try:
            return func(*args, **kw)
        except BrokenMessageError:
            if default is not _missing:
                return default
            raise

    return wrap


def on_header_required(func):
    @functools.wraps(func)
    def wrap(*args, **kw):
        split_header = kw.pop('split_header', False)
        nosplit_header = not split_header

        result = func(*args, **kw)

        split = (nosplit_header and NO_SPLIT) or (split_header and SPLIT) or _missing

        if split is _missing:
            raise RuntimeError

        header = Header().encode(split=split)
        result = b''.join((header, result))

        return result

    return wrap


def use_self_default(func):
    def use_default(self, value=None, values=None):
        if value is None:
            return func(self, self.default_value, values)
        return func(self, value, values)

    return use_default


def needs_buffer(func):
    def needs_buffer(self, buffer, *args, **kwargs):
        if len(buffer) == 0:
            raise BufferExhaustedError
        return func(self, buffer, *args, **kwargs)

    return needs_buffer


def int2ip(value):
    return socket.inet_ntoa(struct.pack('i', value))


class MessageField(object):

    fmt = None
    validators = []

    def __init__(self, name, optional=False, default_value=None, validators=None):
        """
        name -- used when decoding messages to set the key in the
            returned dictionary

        optional -- whether or not a field value must be provided
            when encoding

        default_value -- if optional is False, the value that is
            used if none is specified

        validators -- list of callables that return False if the
            value they're passed is invalid
        """

        if validators is None:
            validators = []

        if self.fmt is not None:
            if self.fmt[0] not in '@=<>!':
                self.format = '<' + self.fmt
            else:
                self.format = self.fmt

        self.name = name
        self.optional = optional
        self._value = default_value
        self.validators = self.__class__.validators + validators

    @property
    def default_value(self):
        if self.optional:
            if self._value is not None:
                return self._value
            raise SkipEncodeError
        raise ValueError("Field '{fname}' is not optional".format(fname=self.name))

    def validate(self, value):
        for validator in self.validators:
            try:
                if not validator(value):
                    raise ValueError
            except Exception:
                raise BrokenMessageError("Invalid value ({}) for field '{}'".format(value, self.name))
        return value

    @use_self_default
    def encode(self, value, values=None):
        try:
            return struct.pack(self.format, self.validate(value))
        except struct.error as exc:
            raise BrokenMessageError(exc)

    @needs_buffer
    def decode(self, buffer, values=None):
        """
        Accepts a string of raw bytes which it will attempt to
        decode into some Python object which is returned. All
        remaining data left in the buffer is also returned which
        may be an empty string.

        Also acecpts a second argument which is a dictionary of the
        fields that have been decoded so far (i.e. occurs before
        this field in `fields` tuple). This allows the decoder to
        adapt it's funtionality based on the value of other fields
        if needs be.

        For example, in the case of A2S_PLAYER resposnes, the field
        `player_count` needs to be accessed at decode-time to determine
        how many player entries to attempt to decode.
        """

        field_size = struct.calcsize(self.format)
        if len(buffer) < field_size:
            raise BufferExhaustedError

        field_data = buffer[:field_size]
        left_overs = buffer[field_size:]

        try:
            return (self.validate(struct.unpack(self.format, field_data)[0]), left_overs)
        except struct.error as exc:
            raise BrokenMessageError(exc)


class ByteField(MessageField):
    fmt = 'B'


class StringField(MessageField):
    fmt = 's'

    @use_self_default
    def encode(self, value, values=None):
        return value.encode('utf8') + b'\x00'

    @needs_buffer
    def decode(self, buffer, values=None):
        terminator = buffer.find(b'\x00')
        if terminator == -1:
            raise BufferExhaustedError('No string terminator')
        field_size = terminator + 1
        field_data = buffer[: field_size - 1]
        left_overs = buffer[field_size:]
        return self.validate(field_data.decode('utf8', 'ignore')), left_overs


class ShortFieldLE(MessageField):  # little-endian
    fmt = '<h'


class ShortFieldBE(MessageField):  # big-endian
    fmt = '>h'


class LongFieldLE(MessageField):  # little-endian
    fmt = '<l'


class LongFieldBE(MessageField):  # big-endian
    fmt = '>l'


class FloatField(MessageField):
    fmt = 'f'


class PlatformField(ByteField):
    @needs_buffer
    def decode(self, buffer, values=None):
        byte, remnant_buffer = super(PlatformField, self).decode(buffer, values)
        return util.Platform(byte), remnant_buffer


class ServerTypeField(ByteField):
    @needs_buffer
    def decode(self, buffer, values=None):
        byte, remnant_buffer = super(ServerTypeField, self).decode(buffer, values)
        return util.ServerType(byte), remnant_buffer


class IpAddrField(LongFieldBE):
    validators = [lambda x: int2ip(x)]


class MessageArrayField(MessageField):
    """
    Represents a nested message within another message that is
    repeated a given number of time (often defined within the
    same message.)
    """

    def __init__(self, name, element, count=None):
        """
        element -- the Message subclass that will attempt to be decoded

        count -- ideally a callable that returns the number of
            'elements' to attempt to decode; count must also present
            a 'minimum' attribute which is minimum number of elements
            that must be decoded or else raise BrokenMessageError

            If count isn't callable (e.g. a number) it will be
            wrapped in a function with the minimum attribute set
            equal to the given 'count' value

            Helper static methods all(), value_of() and at_least()
            are provided which are intended to be used as the
            'count' argument, e.g.

            MessageArrayField("", SubMessage, MessageArrayField.all())

            ... will decode all SubMessages within the buffer
        """

        MessageField.__init__(self, name)
        if count is None:
            count = self.all()
        # Coerces the count argument to be a callable. For example,
        # in most cases count would be a Message.value_of(), however
        # if an integer is provided it will be wrapped in a lambda.
        self.count = count
        if not hasattr(count, '__call__'):  # noqa: B004

            def const_count(values=None):
                return count

            const_count.minimum = count
            self.count = const_count
        self.element = element

    def encode(self, elements, values=None):
        if values is None:
            values = {}

        buf = []
        for i, element in enumerate(elements):
            if not isinstance(element, self.element):
                raise BrokenMessageError(
                    'Element {} ({}) is not instance of {}'.format(i, element, self.element.__name__)
                )
            if i + 1 > self.count(values):
                raise BrokenMessageError('Too many elements')
            buf.append(element.encode())
        if len(buf) < self.count.minimum:
            raise BrokenMessageError('Too few elements')
        return b''.join(buf)

    def decode(self, buffer, values=None):
        if values is None:
            values = {}

        entries = []
        count = 0
        while count < self.count(values):
            # Set start_buffer to the beginning of the buffer so that in
            # the case of buffer exhaustion it can return from the
            # start of the entry, not half-way through it.
            #
            # For example if you had the fields:
            #
            #       ComplexField =
            #           LongField
            #           ShortField
            #
            #       MessageArrayField(ComplexField,
            #                         count=MessageArrayField.all())
            #       ByteField()
            #
            # When attempting to decode the end of the buffer FF FF FF FF 00
            # the first four bytes will be consumed by LongField,
            # however ShortField will fail with BufferExhaustedError as
            # there's only one byte left. However, there is enough left
            # for the trailing ByteField. So when ComplexField
            # propagates ShortField's BufferExhaustedError the buffer will
            # only have the 00 byte remaining. The exception if caught
            # and buffer reverted to FF FF FF FF 00. This is passed
            # to ByteField which consumes one byte and the reamining
            # FF FF FF 00 bytes and stored as message payload.
            #
            # This is very much an edge case. :/
            start_buffer = buffer
            try:
                entry = self.element.decode(buffer)
                buffer = entry.raw_tail
                entries.append(entry)
                count += 1
            except (BufferExhaustedError, BrokenMessageError) as exc:
                # Allow for returning 'at least something' if end of
                # buffer is reached.
                if count < self.count.minimum:
                    raise BrokenMessageError(exc)
                buffer = start_buffer
                break
        return entries, buffer

    @staticmethod
    def value_of(name):
        """
        Reference another field's value as the argument 'count'.
        """

        def field(values, f=None):
            f.minimum = values[name]
            return values[name]

        field.__defaults__ = (field,)
        return field

    @staticmethod
    def all():
        """
        Decode as much as possible from the buffer.

        Note that if a full element field cannot be decoded it will
        return all entries decoded up to that point, and reset the
        buffer to the start of the entry which raised the
        BufferExhaustedError. So it is possible to have addtional
        fields follow a MessageArrayField and have
        count=MessageArrayField.all() as long as the size of the
        trailing fields < size of the MessageArrayField element.
        """

        i = [1]

        def all_(values=None):
            i[0] = i[0] + 1
            return i[0]

        all_.minimum = -1
        return all_

    @staticmethod
    def at_least(minimum):
        """
        Decode at least 'minimum' number of entries.
        """

        i = [1]

        def at_least(values=None):
            i[0] = i[0] + 1
            return i[0]

        at_least.minimum = minimum
        return at_least


class MessageDictField(MessageArrayField):
    """
    Decodes a series of key-value pairs from a message. Functionally
    identical to MessageArrayField except the results are returned as
    a dictionary instead of a list.
    """

    def __init__(self, name, key_field, value_field, count=None):
        """
        key_field and value_field are the respective components
        of the name-value pair that are to be decoded. The fields
        should have unique name strings. Tt is assumed that the
        key-field comes first, followed by the value.

        count is the same as MessageArrayField.
        """

        element = type('KeyValueField', (Message,), {'fields': (key_field, value_field)})
        self.key_field = key_field
        self.value_field = value_field
        MessageArrayField.__init__(self, name, element, count)

    def decode(self, buffer, values=None):
        entries, buffer = MessageArrayField.decode(self, buffer, values)
        entries_dict = {}
        for entry in entries:
            entries_dict[entry[self.key_field.name]] = entry[self.value_field.name]
        return entries_dict, buffer


class Message(collections.abc.MutableMapping):

    fields = ()

    def __init__(self, raw_tail=None, **values):
        self.raw_tail = raw_tail
        self.values = values

    def __getitem__(self, key):
        return self.values[key]

    def __setitem__(self, key, value):
        self.values[key] = value

    def __delitem__(self, key):
        del self.values[key]

    def __len__(self):
        return len(self.values)

    def __iter__(self):
        return iter(self.values)

    def __repr__(self):
        return f'{self.__class__}({self.values})'

    def encode(self, **field_values):
        values = dict(self.values, **field_values)
        buf = []
        for field in self.fields:
            try:
                buf.append(field.encode(values.get(field.name, None), values))
            except SkipEncodeError:
                pass
        return b''.join(buf)

    @classmethod
    @on_broken_default
    def decode(cls, packet):
        buffer = packet
        values = {}
        for field in cls.fields:
            values[field.name], buffer = field.decode(buffer, values)
        return cls(buffer, **values)


class Header(Message):

    fields = (LongFieldLE('split', validators=[lambda x: x in [SPLIT, NO_SPLIT]]),)


class Packet(Message):
    """Message with Header"""

    encode = on_header_required(Message.encode)


class Fragment(Packet):

    fields = (
        LongFieldLE('message_id'),
        ByteField('fragment_count'),
        ByteField('fragment_id'),  # 0-indexed
        ShortFieldLE('mtu'),
    )

    @property
    def is_compressed(self):
        # check MSB (Most Significant Bit)
        return bool(self['message_id'] & (1 << 16))


# TODO: FragmentCompressionData


class InfoRequest(Packet):

    fields = (
        ByteField('request_type', True, 0x54, validators=[lambda x: x == 0x54]),
        StringField('payload', True, 'Source Engine Query'),
    )


class InfoRequestV2(InfoRequest):
    """Protected with challenge version of InfoRequest (A2S_INFO)

    Refs:
     - https://github.com/sqproxy/sqproxy/issues/87
     Official discussions:
     - (part1) https://steamcommunity.com/discussions/forum/14/2989789048633291344/
     - (part2) https://steamcommunity.com/discussions/forum/14/2974028351344359625/

    """

    fields = InfoRequest.fields + (LongFieldLE('challenge', optional=True),)


class InfoResponse(Packet):

    fields = (
        ByteField('response_type', validators=[lambda x: x == 0x49]),
        ByteField('protocol'),
        StringField('server_name'),
        StringField('map'),
        StringField('folder'),
        StringField('game'),
        ShortFieldLE('app_id'),
        ByteField('player_count'),
        ByteField('max_players'),
        ByteField('bot_count'),
        ServerTypeField('server_type'),
        PlatformField('platform'),
        ByteField('password_protected'),  # BooleanField
        ByteField('vac_enabled'),  # BooleanField
        StringField('version'),
        # TODO: EDF
    )


class GetChallengeResponse(Packet):

    fields = (
        ByteField('response_type', True, 0x41, validators=[lambda x: x == 0x41]),
        LongFieldLE('challenge'),
    )


class PlayersRequest(Packet):

    fields = (
        ByteField('request_type', True, 0x55, validators=[lambda x: x == 0x55]),
        LongFieldLE('challenge'),
    )


class PlayerEntry(Packet):

    fields = (
        ByteField('index'),
        StringField('name'),
        LongFieldLE('score'),
        FloatField('duration'),
    )


class PlayersResponse(Packet):

    fields = (
        ByteField('response_type', validators=[lambda x: x == 0x44]),
        ByteField('player_count'),
        MessageArrayField('players', PlayerEntry, MessageArrayField.value_of('player_count')),
    )


class RulesRequest(Packet):

    fields = (
        ByteField('request_type', True, 0x56, validators=[lambda x: x == 0x56]),
        LongFieldLE('challenge'),
    )


class RulesResponse(Packet):

    fields = (
        # A2S_RESPONSE misteriously seems to add a FF FF FF FF
        # long to the beginning of the response which isn't
        # mentioned on the wiki.
        #
        # Behaviour witnessed with TF2 server 94.23.226.200:2045
        # LongFieldLE("long"),
        ByteField('response_type', validators=[lambda x: x == 0x45]),
        ShortFieldLE('rule_count'),
        MessageDictField(
            'rules',
            StringField('key'),
            StringField('value'),
            MessageArrayField.value_of('rule_count'),
        ),
    )


# For Master Server
class MSAddressEntryPortField(MessageField):
    fmt = '!H'


class MSAddressEntryIPField(MessageField):
    @needs_buffer
    def decode(self, buffer, values=None):
        if len(buffer) < 4:
            raise BufferExhaustedError
        field_data = buffer[:4]
        left_overs = buffer[4:]
        return '.'.join(str(b) for b in struct.unpack(b'<BBBB', field_data)), left_overs


class MasterServerRequest(Packet):

    fields = (ByteField('request_type', True, 0x31), ByteField('region'), StringField('address'), StringField('filter'))


class MSAddressEntry(Message):

    fields = (
        MSAddressEntryIPField('host'),
        MSAddressEntryPortField('port'),
    )

    @property
    def is_null(self):
        return self['host'] == '0.0.0.0' and self['port'] == 0


class MasterServerResponse(Packet):

    fields = (
        # The first two fields are always FF FF FF FF and 66 0A
        # and can be ignored.
        MSAddressEntryIPField('start_host'),
        MSAddressEntryPortField('start_port'),
        MessageArrayField(
            'addresses',
            MSAddressEntry,
            MessageArrayField.all(),
        ),
    )
