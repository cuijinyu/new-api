package common

import (
	"errors"

	"github.com/QuantumNous/new-api/constant"
)

var ErrRequestBodyTooLarge = errors.New("request body too large")

const (
	defaultMaxRequestBodyMB            = 128
	defaultAnonymousRequestBodyLimitKB = 512
)

func IsRequestBodyTooLargeError(err error) bool {
	return errors.Is(err, ErrRequestBodyTooLarge)
}

func GetMaxRequestBodyBytes() int64 {
	limitMB := constant.MaxRequestBodyMB
	if limitMB <= 0 {
		limitMB = defaultMaxRequestBodyMB
	}
	return int64(limitMB) << 20
}

func GetAnonymousRequestBodyLimitBytes() int64 {
	limitKB := constant.AnonymousRequestBodyLimitKB
	if limitKB < 0 {
		limitKB = defaultAnonymousRequestBodyLimitKB
	}
	return int64(limitKB) << 10
}
