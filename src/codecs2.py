import codecs


# Sample implementation of encoder/decoder provider for a binary transform.
# This transformation is self-inverting, so no inverse is defined.
# A nested function like this defines a stateless implementation.
# The outer function will be passed arbitrary keyword arguments for
# configuration, and the inner function will be passed the data to transform.
def xor(pattern=b''):
    # If transforming the data has implications for future attempts
    # (i.e. the transformation has more complex state than "data at the
    # current end of the stream is incomplete"), the closure can be used to
    # record that.
    # Or it can just be used for pre-calculation, like:
    count = len(pattern)
    def _transform(data, offset):
        # Returns a tuple of (transformed result, amount consumed).
        # Note that in the general case, the amount consumed is not necessarily
        # the length of the transformed result (but it is here).
        # It may transform only partially, but transforming nothing
        # indicates that the transformation cannot proceed past this point.
        if len(data) - offset < count:
            return (b'', 0)
        return (bytes(pattern[i] ^ data[i+offset] for i in range(count)), count)
    return _transform, b''


# Example of a bytes-to-text transform (decoding).
# The built-in shift-JIS decoder will consider the last byte of the data
# (and possibly error on it) even if it's the first byte of a multibyte
# sequence. We want to stop before that byte, regardless of the error
# handling strategy; LBYL is easier this time.
def sjis(errors='strict'):
    _impl = codecs.lookup('sjis').decode
    def _transform(data, offset):
        if not data: # avoid issues later
            return '', 0
        try:
            result, size = _impl(data[offset:], errors=errors)
        except UnicodeDecodeError as e: # must be 'strict'.
            # start and end *of the erroneous sequence*.
            sjis, d, start, end, msg = e.args
            assert sjis == 'shift_jis'
            assert d == data
            return _impl(data[offset:offset+start], errors=errors)
        if errors == 'strict':
            # if we were successful, then the last byte was kosher.
            return result, size
        # otherwise, figure out if the last byte is the first of a pair.
        # It needs to be in range, and we also check whether removing it
        # would affect the result of decoding the previous bytes.
        if data[-1] < 0x81 or 0xa0 <= data[-1] <= 0xdf or data[-1] >= 0xfd:
            return result, size
        without_last, count = _impl(data[offset:-1], errors=errors)
        if result.startswith(without_last):
            return without_last, count
        return result, size
    return _transform, ''


def transform(data, provider, full=True, **kwargs):
    chunks = []
    # We can't rely on the transformer to give us an "empty" joiner,
    # because it's valid for an empty input to produce a non-empty result.
    # TODO: use annotations for inference instead.
    transformer, joiner = provider(**kwargs)
    offset = 0
    while True:
        chunk, consumed = transformer(data, offset)
        # The transformer is allowed - once - to consume nothing and
        # output non-zero data for a "footer" or "padding". Therefore,
        # we extend first before checking for a stopping point.
        chunks.append(chunk)
        offset += consumed
        if not consumed:
            break
    result = joiner.join(chunks)
    if full and (offset != len(data)):
        raise ValueError(result, len(data) - offset)
    return result
