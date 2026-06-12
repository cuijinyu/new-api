package middleware

import (
	"github.com/QuantumNous/new-api/common"
	"github.com/gin-gonic/gin"
)

func BodyStorageCleanup() gin.HandlerFunc {
	return func(c *gin.Context) {
		defer func() {
			value, ok := c.Get(common.KeyRequestBody)
			if !ok {
				return
			}
			if storage, ok := value.(common.BodyStorage); ok {
				_ = storage.Close()
			}
		}()
		c.Next()
	}
}
