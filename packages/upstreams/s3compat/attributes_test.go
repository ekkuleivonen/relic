package s3compat

import (
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"testing"

	"github.com/elei-io/pithosys/packages/storage"
)

func TestAttributesFromHead(t *testing.T) {
	tests := []struct {
		name     string
		upstream Upstream
		want     storage.ObjectAttributes
	}{
		{
			name:     "aws",
			upstream: UpstreamAWS,
			want: storage.ObjectAttributes{
				"upstream": map[string]any{
					"etag":          "\"fba9dede5f27731c9771645a39863328\"",
					"size":          int64(434234),
					"last_modified": "2006-01-01T12:00:00Z",
					"header": map[string]any{
						"accept_ranges": "bytes",
						"content_type":  "image/jpeg",
					},
					"metadata": map[string]any{
						"source": "camera",
					},
					"s3": map[string]any{
						"storage_class": "STANDARD",
						"version_id":    "3HL4kqtJlcpXroDTDmjVBH40Nrjfkd",
					},
				},
			},
		},
		{
			name:     "r2",
			upstream: UpstreamR2,
			want: storage.ObjectAttributes{
				"upstream": map[string]any{
					"etag":          "\"6f5902ac237024bdd0c176cb93063dc4\"",
					"size":          int64(434234),
					"last_modified": "2026-06-26T01:00:00Z",
					"header": map[string]any{
						"accept_ranges": "bytes",
						"content_type":  "image/jpeg",
					},
					"metadata": map[string]any{
						"source": "camera",
					},
				},
			},
		},
		{
			name:     "b2",
			upstream: UpstreamB2,
			want: storage.ObjectAttributes{
				"upstream": map[string]any{
					"etag":          "\"85f30635602dc09bd85957a6e82a2c21\"",
					"size":          int64(434234),
					"last_modified": "2022-01-28T23:12:33Z",
					"header": map[string]any{
						"accept_ranges": "bytes",
						"cache_control": "max-age=0, no-cache, no-store",
						"content_type":  "image/jpeg",
					},
					"s3": map[string]any{
						"version_id": "4_z6145af89f355ac2f74ed0c1b_f416a807037a7ee2a_d20220128_m231233_c004_v0402000_t0056",
					},
					"b2": map[string]any{
						"live_read_enabled":   true,
						"live_read_part_size": int64(5000),
					},
				},
			},
		},
		{
			name:     "gcp",
			upstream: UpstreamGCP,
			want: storage.ObjectAttributes{
				"upstream": map[string]any{
					"etag":          "\"2218880ef78838266ecd7d4c1b742a0e\"",
					"size":          int64(328),
					"last_modified": "2018-05-30T20:36:34Z",
					"header": map[string]any{
						"accept_ranges": "bytes",
						"cache_control": "private, max-age=0",
						"content_type":  "image/jpg",
					},
					"gcp": map[string]any{
						"generation":              "1486161811706000",
						"hash":                    []string{"crc32c=HBrbzQ==", "md5=OCydg52+pPG1Bwawjsl7DA=="},
						"metageneration":          "15",
						"storage_class":           "STANDARD",
						"stored_content_encoding": "identity",
						"stored_content_length":   int64(328),
					},
				},
			},
		},
		{
			name:     "rustfs",
			upstream: UpstreamRustFS,
			want: storage.ObjectAttributes{
				"upstream": map[string]any{
					"etag":          "\"d41d8cd98f00b204e9800998ecf8427e\"",
					"size":          int64(434234),
					"last_modified": "2026-06-26T01:00:00Z",
					"header": map[string]any{
						"accept_ranges": "bytes",
						"content_type":  "image/jpeg",
					},
					"metadata": map[string]any{
						"source": "camera",
					},
					"s3": map[string]any{
						"storage_class": "STANDARD",
					},
				},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			fixture := readHEADFixture(t, tt.name)

			got, err := AttributesFromHead(tt.upstream, fixture.Response)
			if err != nil {
				t.Fatalf("AttributesFromHead returned error: %v", err)
			}

			if !reflect.DeepEqual(got, tt.want) {
				t.Fatalf("AttributesFromHead mismatch\n got: %#v\nwant: %#v", got, tt.want)
			}
		})
	}
}

func TestAttributesFromHeadRejectsUnsupportedUpstream(t *testing.T) {
	fixture := readHEADFixture(t, "aws")

	_, err := AttributesFromHead(Upstream("unsupported"), fixture.Response)
	if err == nil {
		t.Fatal("AttributesFromHead returned nil error, want unsupported upstream error")
	}
}

func readHEADFixture(t *testing.T, upstream string) rawFixture {
	t.Helper()

	path := filepath.Join("testdata", "mocks", "HEAD", upstream+".json")
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read fixture %s: %v", path, err)
	}

	var fixture rawFixture
	if err := json.Unmarshal(data, &fixture); err != nil {
		t.Fatalf("decode fixture %s: %v", path, err)
	}

	return fixture
}

type rawFixture struct {
	Response RawHTTPResponse `json:"response"`
}
