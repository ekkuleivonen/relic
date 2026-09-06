package auth

import (
	"testing"
	"time"
)

func TestCallbackStateMustMatchBrowserCookie(t *testing.T) {
	provider := &OIDCProvider{secret: []byte("unit-test-signing-material")}
	signed, err := provider.SignState("browser-state", time.Now().Add(time.Minute))
	if err != nil {
		t.Fatal(err)
	}
	for _, state := range []string{"", "attacker-state"} {
		if err := provider.VerifyCallbackState(state, signed); err == nil {
			t.Fatalf("accepted mismatched state %q", state)
		}
	}
	if err := provider.VerifyCallbackState("browser-state", signed); err != nil {
		t.Fatal(err)
	}
	expired, err := provider.SignState("browser-state", time.Now().Add(-time.Minute))
	if err != nil {
		t.Fatal(err)
	}
	if err := provider.VerifyCallbackState("browser-state", expired); err == nil {
		t.Fatal("accepted expired state")
	}
}
