class AppTestStringIO:
    def test_stringio(self):
        import io
        sio = io.StringIO()
        sio.write(u'Hello ')
        sio.write(u'world')
        assert sio.getvalue() == u'Hello world'

        assert io.StringIO(u"hello").read() == u'hello'

    def test_capabilities(self):
        import io
        sio = io.StringIO()
        assert sio.readable()
        assert sio.writable()
        assert sio.seekable()
        sio.close()

    def test_closed(self):
        import io
        sio = io.StringIO()
        sio.close()
        raises(ValueError, sio.read, 1)
        raises(ValueError, sio.write, u"text")

    def testRead(self):
        import io
        buf = u"1234567890"
        sio = io.StringIO(buf)

        assert buf[:1] == sio.read(1)
        assert buf[1:5] == sio.read(4)
        assert buf[5:] == sio.read(900)
        assert u"" == sio.read()

    def test_seek(self):
        import io

        s = u"1234567890"
        sio = io.StringIO(s)

        sio.read(5)
        sio.seek(0)
        r = sio.read()
        assert r == s

        sio.seek(3)
        r = sio.read()
        assert r == s[3:]
        raises(TypeError, sio.seek, 0.0)

    def test_write_error(self):
        import io

        exc_info = raises(TypeError, io.StringIO, 3)
        assert "int" in exc_info.value.args[0]

        sio = io.StringIO(u"")
        exc_info = raises(TypeError, sio.write, 3)
        assert "int" in exc_info.value.args[0]