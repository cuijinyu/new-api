package common

import (
	"io"

	basecommon "github.com/QuantumNous/new-api/common"
)

func NewOutboundJSONBody(data []byte) (body io.Reader, size int64, closer io.Closer, err error) {
	storage, err := basecommon.CreateBodyStorage(data)
	if err != nil {
		return nil, 0, nil, err
	}
	return storage, storage.Size(), storage, nil
}
