from pathlib import Path
from kelpmesh.state.engine import StateEngine
import tempfile


class TestStateEngine:
    def setup_method(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.state = StateEngine(self.tmpdir)

    def test_record_and_check(self):
        self.state.record_run("test_model", "abc123", 100)
        assert self.state.is_up_to_date("test_model", "abc123")
        assert not self.state.is_up_to_date("test_model", "def456")

    def test_get_state(self):
        self.state.record_run("test_model", "abc123", 50)
        state = self.state.get_state("test_model")
        assert state is not None
        assert state["hash"] == "abc123"
        assert state["row_count"] == 50
        assert state["model_name"] == "test_model"

    def test_get_nonexistent(self):
        state = self.state.get_state("nonexistent")
        assert state is None

    def test_reset_single(self):
        self.state.record_run("model_a", "hash_a", 10)
        self.state.record_run("model_b", "hash_b", 20)
        self.state.reset("model_a")
        assert self.state.get_state("model_a") is None
        assert self.state.get_state("model_b") is not None

    def test_reset_all(self):
        self.state.record_run("model_a", "hash_a", 10)
        self.state.record_run("model_b", "hash_b", 20)
        self.state.reset()
        assert self.state.get_state("model_a") is None
        assert self.state.get_state("model_b") is None

    def test_update_existing(self):
        self.state.record_run("model", "old_hash", 10)
        self.state.record_run("model", "new_hash", 20)
        state = self.state.get_state("model")
        assert state["hash"] == "new_hash"
        assert state["row_count"] == 20

    def test_get_all_states(self):
        self.state.record_run("a", "h1", 1)
        self.state.record_run("b", "h2", 2)
        all_states = self.state.get_all_states()
        assert len(all_states) == 2
