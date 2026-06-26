package s3compat

import (
	"encoding/json"
	"fmt"
	"strings"
)

type Credentials struct {
	AccessKeyID     string `json:"access_key_id"`
	SecretAccessKey string `json:"secret_access_key"`
	SessionToken    string `json:"session_token,omitempty"`
}

func ParseCredentials(data []byte) (Credentials, error) {
	var credentials Credentials
	if err := json.Unmarshal(data, &credentials); err != nil {
		return Credentials{}, fmt.Errorf("parse s3-compatible credentials: %w", err)
	}

	credentials.AccessKeyID = strings.TrimSpace(credentials.AccessKeyID)
	credentials.SecretAccessKey = strings.TrimSpace(credentials.SecretAccessKey)
	credentials.SessionToken = strings.TrimSpace(credentials.SessionToken)

	if credentials.AccessKeyID == "" {
		return Credentials{}, fmt.Errorf("access_key_id is required")
	}
	if credentials.SecretAccessKey == "" {
		return Credentials{}, fmt.Errorf("secret_access_key is required")
	}

	return credentials, nil
}
