import pytest

from mitmproxy.addons.modifyheaders import ModifyHeaders
from mitmproxy.addons.modifyheaders import parse_modify_spec
from mitmproxy.test import taddons
from mitmproxy.test import tflow
from mitmproxy.test.tutils import tresp


def test_parse_modify_spec():
    spec = parse_modify_spec("/foo/bar/voing", True)
    assert spec.matches.pattern == "foo"
    assert spec.subject == b"bar"
    assert spec.read_replacement() == b"voing"

    spec = parse_modify_spec("/foo/bar/vo/ing/", False)
    assert spec.matches.pattern == "foo"
    assert spec.subject == b"bar"
    assert spec.read_replacement() == b"vo/ing/"

    spec = parse_modify_spec("/bar/voing", False)
    assert spec.matches(tflow.tflow())
    assert spec.subject == b"bar"
    assert spec.read_replacement() == b"voing"

    with pytest.raises(ValueError, match="Invalid regular expression"):
        parse_modify_spec("/[/two", True)


class TestModifyHeaders:
    def test_configure(self):
        mh = ModifyHeaders()
        with taddons.context(mh) as tctx:
            with pytest.raises(Exception, match="Cannot parse modify_headers"):
                tctx.configure(mh, modify_headers=["/"])
            tctx.configure(mh, modify_headers=["/foo/bar/voing"])

    def test_modify_headers(self):
        mh = ModifyHeaders()
        with taddons.context(mh) as tctx:
            tctx.configure(mh, modify_headers=["/~q/one/two", "/~s/one/three"])
            f = tflow.tflow()
            f.request.headers["one"] = "xxx"
            mh.requestheaders(f)
            assert f.request.headers["one"] == "two"

            f = tflow.tflow(resp=True)
            f.response.headers["one"] = "xxx"
            mh.responseheaders(f)
            assert f.response.headers["one"] == "three"

            tctx.configure(mh, modify_headers=["/~s/one/two", "/~s/one/three"])
            f = tflow.tflow(resp=True)
            f.request.headers["one"] = "xxx"
            f.response.headers["one"] = "xxx"
            mh.responseheaders(f)
            assert f.response.headers.get_all("one") == ["two", "three"]

            tctx.configure(mh, modify_headers=["/~q/one/two", "/~q/one/three"])
            f = tflow.tflow()
            f.request.headers["one"] = "xxx"
            mh.requestheaders(f)
            assert f.request.headers.get_all("one") == ["two", "three"]

            # test removal of existing headers
            tctx.configure(mh, modify_headers=["/~q/one/", "/~s/one/"])
            f = tflow.tflow()
            f.request.headers["one"] = "xxx"
            mh.requestheaders(f)
            assert "one" not in f.request.headers

            f = tflow.tflow(resp=True)
            f.response.headers["one"] = "xxx"
            mh.responseheaders(f)
            assert "one" not in f.response.headers

            tctx.configure(mh, modify_headers=["/one/"])
            f = tflow.tflow()
            f.request.headers["one"] = "xxx"
            mh.requestheaders(f)
            assert "one" not in f.request.headers

            f = tflow.tflow(resp=True)
            f.response.headers["one"] = "xxx"
            mh.responseheaders(f)
            assert "one" not in f.response.headers

            # test modifying a header that is also part of the filter expression
            # https://github.com/mitmproxy/mitmproxy/issues/4245
            tctx.configure(
                mh,
                modify_headers=[
                    "/~hq ^user-agent:.+Mozilla.+$/user-agent/Definitely not Mozilla ;)"
                ],
            )
            f = tflow.tflow()
            f.request.headers["user-agent"] = "Hello, it's me, Mozilla"
            mh.requestheaders(f)
            assert "Definitely not Mozilla ;)" == f.request.headers["user-agent"]

    @pytest.mark.parametrize("take", [True, False])
    def test_taken(self, take):
        mh = ModifyHeaders()
        with taddons.context(mh) as tctx:
            tctx.configure(mh, modify_headers=["/content-length/42"])
            f = tflow.tflow()
            if take:
                f.response = tresp()
            mh.requestheaders(f)
            assert (f.request.headers["content-length"] == "42") ^ take

            f = tflow.tflow(resp=True)
            if take:
                f.kill()
            mh.responseheaders(f)
            assert (f.response.headers["content-length"] == "42") ^ take


class TestModifyHeadersFile:
    def test_simple(self, tmpdir):
        mh = ModifyHeaders()
        with taddons.context(mh) as tctx:
            tmpfile = tmpdir.join("replacement")
            tmpfile.write("two")
            tctx.configure(mh, modify_headers=["/~q/one/@" + str(tmpfile)])
            f = tflow.tflow()
            f.request.headers["one"] = "xxx"
            mh.requestheaders(f)
            assert f.request.headers["one"] == "two"

    async def test_nonexistent(self, tmpdir, caplog):
        mh = ModifyHeaders()
        with taddons.context(mh) as tctx:
            with pytest.raises(
                Exception, match="Cannot parse modify_headers .* Invalid file path"
            ):
                tctx.configure(mh, modify_headers=["/~q/foo/@nonexistent"])

            tmpfile = tmpdir.join("replacement")
            tmpfile.write("bar")
            tctx.configure(mh, modify_headers=["/~q/foo/@" + str(tmpfile)])
            tmpfile.remove()
            f = tflow.tflow()
            f.request.content = b"foo"
            mh.requestheaders(f)
            assert "Could not read" in caplog.text
