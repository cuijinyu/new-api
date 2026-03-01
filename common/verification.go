package common

import (
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
)

type verificationValue struct {
	code string
	time time.Time
}

const (
	EmailVerificationPurpose = "v"
	PasswordResetPurpose     = "r"
)

var verificationMutex sync.Mutex
var verificationMap map[string]verificationValue
var verificationMapMaxSize = 10
var VerificationValidMinutes = 10

func GenerateVerificationCode(length int) string {
	code := uuid.New().String()
	code = strings.Replace(code, "-", "", -1)
	if length == 0 {
		return code
	}
	return code[:length]
}

// redisVerifyKey 构造 Redis Key
func redisVerifyKey(key, purpose string) string {
	return "verify:" + purpose + ":" + key
}

func RegisterVerificationCodeWithKey(key string, code string, purpose string) {
	if RedisEnabled {
		expiration := time.Duration(VerificationValidMinutes) * time.Minute
		err := RedisSet(redisVerifyKey(key, purpose), code, expiration)
		if err != nil {
			SysError("RegisterVerificationCodeWithKey redis error: " + err.Error())
		}
		return
	}
	// 降级：内存存储
	verificationMutex.Lock()
	defer verificationMutex.Unlock()
	verificationMap[purpose+key] = verificationValue{
		code: code,
		time: time.Now(),
	}
	if len(verificationMap) > verificationMapMaxSize {
		removeExpiredPairs()
	}
}

func VerifyCodeWithKey(key string, code string, purpose string) bool {
	if RedisEnabled {
		val, err := RedisGet(redisVerifyKey(key, purpose))
		if err != nil {
			// redis.Nil 表示 key 不存在或已过期
			return false
		}
		return val == code
	}
	// 降级：内存校验
	verificationMutex.Lock()
	defer verificationMutex.Unlock()
	value, okay := verificationMap[purpose+key]
	now := time.Now()
	if !okay || int(now.Sub(value.time).Seconds()) >= VerificationValidMinutes*60 {
		return false
	}
	return code == value.code
}

func DeleteKey(key string, purpose string) {
	if RedisEnabled {
		err := RedisDel(redisVerifyKey(key, purpose))
		if err != nil {
			SysError("DeleteKey redis error: " + err.Error())
		}
		return
	}
	// 降级：内存删除
	verificationMutex.Lock()
	defer verificationMutex.Unlock()
	delete(verificationMap, purpose+key)
}

// no lock inside, so the caller must lock the verificationMap before calling!
func removeExpiredPairs() {
	now := time.Now()
	for key := range verificationMap {
		if int(now.Sub(verificationMap[key].time).Seconds()) >= VerificationValidMinutes*60 {
			delete(verificationMap, key)
		}
	}
}

func init() {
	verificationMutex.Lock()
	defer verificationMutex.Unlock()
	verificationMap = make(map[string]verificationValue)
}
