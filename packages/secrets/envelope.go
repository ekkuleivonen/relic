package secrets

const AlgorithmXChaCha20Poly1305 = "xchacha20-poly1305"

type Envelope struct {
	KeyID      string `json:"key_id"`
	Algorithm  string `json:"algorithm"`
	Nonce      []byte `json:"nonce"`
	Ciphertext []byte `json:"ciphertext"`
}
