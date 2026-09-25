from app.store import Store


def test_conversation_messages_and_restart_persistence(tmp_path):
    db = str(tmp_path / "muse.db")
    store = Store(db)
    conv = store.create_conversation("Milestone chat", "opencode_server", "opencode/big-pickle")
    store.add_message(conv["id"], "user", "make me a file called hello.md")
    store.add_message(conv["id"], "assistant", "Created hello.md")
    store.add_artifact(kind="document", path="/tmp/work/hello.md", title="hello.md",
                       content="# hello", conversation_id=conv["id"])
    store.close()

    reopened = Store(db)
    convs = reopened.list_conversations()
    assert len(convs) == 1 and convs[0]["title"] == "Milestone chat"
    msgs = reopened.list_messages(conv["id"])
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    arts = reopened.list_artifacts()
    assert arts[0]["title"] == "hello.md" and arts[0]["content"] == "# hello"
    assert reopened.find_artifact_by_path("/tmp/work/hello.md") is not None
    reopened.close()


def test_approval_lifecycle(tmp_path):
    store = Store(str(tmp_path / "muse.db"))
    conv = store.create_conversation("c", "opencode_server")
    ap = store.add_approval("write_file", '{"path": "hello.md"}',
                            conversation_id=conv["id"], engine_permission_id="perm_1")
    assert ap["status"] == "pending"
    done = store.resolve_approval(ap["id"], "approved")
    assert done["status"] == "approved" and done["resolved_at"]
    assert store.list_approvals(status="pending") == []
    store.close()


def test_engine_session_link(tmp_path):
    store = Store(str(tmp_path / "muse.db"))
    conv = store.create_conversation("c", "opencode_server")
    store.set_engine_session(conv["id"], "ses_123")
    assert store.get_conversation(conv["id"])["engine_session_id"] == "ses_123"
    store.close()
