package s3compat

import (
	"strings"
	"testing"
)

func TestParseCredentials(t *testing.T) {
	data := []byte(`{
		"access_key_id": "  access-key  ",
		"secret_access_key": "  secret-key  ",
		"session_token": "  session-token  "
	}`)

	credentials, err := ParseCredentials(data)
	if err != nil {
		t.Fatalf("ParseCredentials returned error: %v", err)
	}

	if credentials.AccessKeyID != "access-key" {
		t.Fatalf("AccessKeyID = %q, want access-key", credentials.AccessKeyID)
	}
	if credentials.SecretAccessKey != "secret-key" {
		t.Fatalf("SecretAccessKey = %q, want secret-key", credentials.SecretAccessKey)
	}
	if credentials.SessionToken != "session-token" {
		t.Fatalf("SessionToken = %q, want session-token", credentials.SessionToken)
	}
}

func TestParseCredentialsAllowsMissingSessionToken(t *testing.T) {
	data := []byte(`{
		"access_key_id": "access-key",
		"secret_access_key": "secret-key"
	}`)

	credentials, err := ParseCredentials(data)
	if err != nil {
		t.Fatalf("ParseCredentials returned error: %v", err)
	}

	if credentials.SessionToken != "" {
		t.Fatalf("SessionToken = %q, want empty", credentials.SessionToken)
	}
}

func TestParseCredentialsRejectsMissingAccessKeyID(t *testing.T) {
	_, err := ParseCredentials([]byte(`{
		"secret_access_key": "secret-key"
	}`))
	if err == nil {
		t.Fatal("ParseCredentials returned nil error, want missing access_key_id error")
	}
	if !strings.Contains(err.Error(), "access_key_id is required") {
		t.Fatalf("error = %q, want access_key_id required", err.Error())
	}
}

func TestParseCredentialsRejectsMissingSecretAccessKey(t *testing.T) {
	_, err := ParseCredentials([]byte(`{
		"access_key_id": "access-key"
	}`))
	if err == nil {
		t.Fatal("ParseCredentials returned nil error, want missing secret_access_key error")
	}
	if !strings.Contains(err.Error(), "secret_access_key is required") {
		t.Fatalf("error = %q, want secret_access_key required", err.Error())
	}
}

func TestParseCredentialsDoesNotLeakSecretInError(t *testing.T) {
	_, err := ParseCredentials([]byte(`{
		"access_key_id": "access-key",
		"secret_access_key": "  "
	}`))
	if err == nil {
		t.Fatal("ParseCredentials returned nil error, want validation error")
	}
	if strings.Contains(err.Error(), "access-key") {
		t.Fatalf("error leaked access key ID: %q", err.Error())
	}
}

func TestParseCredentialsRejectsInvalidJSON(t *testing.T) {
	_, err := ParseCredentials([]byte(`{`))
	if err == nil {
		t.Fatal("ParseCredentials returned nil error, want invalid JSON error")
	}
}
