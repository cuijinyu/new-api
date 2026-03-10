package common

import (
	"context"
	"errors"
	"fmt"
	"os"
	"reflect"
	"strconv"
	"strings"
	"time"

	"github.com/go-redis/redis/v8"
	"gorm.io/gorm"
)

var RDB *redis.Client
var SecondaryRDB *redis.Client
var RedisEnabled = true
var RedisDualWriteEnabled bool
var RedisDualWriteStrict bool

func RedisKeyCacheSeconds() int {
	return SyncFrequency
}

// InitRedisClient This function is called after init()
func InitRedisClient() (err error) {
	if os.Getenv("REDIS_CONN_STRING") == "" {
		RedisEnabled = false
		SysLog("REDIS_CONN_STRING not set, Redis is not enabled")
		return nil
	}
	if os.Getenv("SYNC_FREQUENCY") == "" {
		SysLog("SYNC_FREQUENCY not set, use default value 60")
		SyncFrequency = 60
	}
	SysLog("Redis is enabled")
	opt, err := redis.ParseURL(os.Getenv("REDIS_CONN_STRING"))
	if err != nil {
		FatalLog("failed to parse Redis connection string: " + err.Error())
	}
	opt.PoolSize = GetEnvOrDefault("REDIS_POOL_SIZE", 10)
	RDB = redis.NewClient(opt)

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	_, err = RDB.Ping(ctx).Result()
	if err != nil {
		FatalLog("Redis ping test failed: " + err.Error())
	}
	if DebugEnabled {
		SysLog(fmt.Sprintf("Redis connected to %s", opt.Addr))
		SysLog(fmt.Sprintf("Redis database: %d", opt.DB))
	}

	RedisDualWriteStrict = GetEnvOrDefaultBool("REDIS_DUAL_WRITE_STRICT", false)
	secondaryConn := os.Getenv("REDIS_DUAL_WRITE_CONN_STRING")
	if secondaryConn != "" {
		secOpt, secErr := redis.ParseURL(secondaryConn)
		if secErr != nil {
			if RedisDualWriteStrict {
				FatalLog("failed to parse REDIS_DUAL_WRITE_CONN_STRING: " + secErr.Error())
			}
			SysError("dual-write disabled, failed to parse secondary redis connection string: " + secErr.Error())
			return nil
		}
		secOpt.PoolSize = GetEnvOrDefault("REDIS_DUAL_WRITE_POOL_SIZE", opt.PoolSize)
		SecondaryRDB = redis.NewClient(secOpt)

		_, secErr = SecondaryRDB.Ping(ctx).Result()
		if secErr != nil {
			if RedisDualWriteStrict {
				FatalLog("secondary redis ping test failed: " + secErr.Error())
			}
			SysError("dual-write disabled, secondary redis ping test failed: " + secErr.Error())
			return err
		}
		RedisDualWriteEnabled = true
		RDB.AddHook(newRedisDualWriteHook(SecondaryRDB, RedisDualWriteStrict))
		SysLog("Redis dual-write enabled")
	}
	return err
}

func ParseRedisOption() *redis.Options {
	opt, err := redis.ParseURL(os.Getenv("REDIS_CONN_STRING"))
	if err != nil {
		FatalLog("failed to parse Redis connection string: " + err.Error())
	}
	return opt
}

func RedisSet(key string, value string, expiration time.Duration) error {
	if DebugEnabled {
		SysLog(fmt.Sprintf("Redis SET: key=%s, value=%s, expiration=%v", key, value, expiration))
	}
	ctx := context.Background()
	return RDB.Set(ctx, key, value, expiration).Err()
}

func RedisGet(key string) (string, error) {
	if DebugEnabled {
		SysLog(fmt.Sprintf("Redis GET: key=%s", key))
	}
	ctx := context.Background()
	val, err := RDB.Get(ctx, key).Result()
	return val, err
}

//func RedisExpire(key string, expiration time.Duration) error {
//	ctx := context.Background()
//	return RDB.Expire(ctx, key, expiration).Err()
//}
//
//func RedisGetEx(key string, expiration time.Duration) (string, error) {
//	ctx := context.Background()
//	return RDB.GetSet(ctx, key, expiration).Result()
//}

func RedisDel(key string) error {
	if DebugEnabled {
		SysLog(fmt.Sprintf("Redis DEL: key=%s", key))
	}
	ctx := context.Background()
	return RDB.Del(ctx, key).Err()
}

func RedisDelKey(key string) error {
	if DebugEnabled {
		SysLog(fmt.Sprintf("Redis DEL Key: key=%s", key))
	}
	ctx := context.Background()
	return RDB.Del(ctx, key).Err()
}

func RedisHSetObj(key string, obj interface{}, expiration time.Duration) error {
	if DebugEnabled {
		SysLog(fmt.Sprintf("Redis HSET: key=%s, obj=%+v, expiration=%v", key, obj, expiration))
	}
	ctx := context.Background()

	data := make(map[string]interface{})

	// 使用反射遍历结构体字段
	v := reflect.ValueOf(obj).Elem()
	t := v.Type()
	for i := 0; i < v.NumField(); i++ {
		field := t.Field(i)
		value := v.Field(i)

		// Skip DeletedAt field
		if field.Type.String() == "gorm.DeletedAt" {
			continue
		}

		// 处理指针类型
		if value.Kind() == reflect.Ptr {
			if value.IsNil() {
				data[field.Name] = ""
				continue
			}
			value = value.Elem()
		}

		// 处理布尔类型
		if value.Kind() == reflect.Bool {
			data[field.Name] = strconv.FormatBool(value.Bool())
			continue
		}

		// 其他类型直接转换为字符串
		data[field.Name] = fmt.Sprintf("%v", value.Interface())
	}

	txn := RDB.TxPipeline()
	txn.HSet(ctx, key, data)

	// 只有在 expiration 大于 0 时才设置过期时间
	if expiration > 0 {
		txn.Expire(ctx, key, expiration)
	}

	_, err := txn.Exec(ctx)
	if err != nil {
		return fmt.Errorf("failed to execute transaction: %w", err)
	}
	return nil
}

func RedisHGetObj(key string, obj interface{}) error {
	if DebugEnabled {
		SysLog(fmt.Sprintf("Redis HGETALL: key=%s", key))
	}
	ctx := context.Background()

	result, err := RDB.HGetAll(ctx, key).Result()
	if err != nil {
		return fmt.Errorf("failed to load hash from Redis: %w", err)
	}

	if len(result) == 0 {
		return fmt.Errorf("key %s not found in Redis", key)
	}

	// Handle both pointer and non-pointer values
	val := reflect.ValueOf(obj)
	if val.Kind() != reflect.Ptr {
		return fmt.Errorf("obj must be a pointer to a struct, got %T", obj)
	}

	v := val.Elem()
	if v.Kind() != reflect.Struct {
		return fmt.Errorf("obj must be a pointer to a struct, got pointer to %T", v.Interface())
	}

	t := v.Type()
	for i := 0; i < v.NumField(); i++ {
		field := t.Field(i)
		fieldName := field.Name
		if value, ok := result[fieldName]; ok {
			fieldValue := v.Field(i)

			// Handle pointer types
			if fieldValue.Kind() == reflect.Ptr {
				if value == "" {
					continue
				}
				if fieldValue.IsNil() {
					fieldValue.Set(reflect.New(fieldValue.Type().Elem()))
				}
				fieldValue = fieldValue.Elem()
			}

			// Enhanced type handling for Token struct
			switch fieldValue.Kind() {
			case reflect.String:
				fieldValue.SetString(value)
			case reflect.Int, reflect.Int64:
				intValue, err := strconv.ParseInt(value, 10, 64)
				if err != nil {
					return fmt.Errorf("failed to parse int field %s: %w", fieldName, err)
				}
				fieldValue.SetInt(intValue)
			case reflect.Bool:
				boolValue, err := strconv.ParseBool(value)
				if err != nil {
					return fmt.Errorf("failed to parse bool field %s: %w", fieldName, err)
				}
				fieldValue.SetBool(boolValue)
			case reflect.Struct:
				// Special handling for gorm.DeletedAt
				if fieldValue.Type().String() == "gorm.DeletedAt" {
					if value != "" {
						timeValue, err := time.Parse(time.RFC3339, value)
						if err != nil {
							return fmt.Errorf("failed to parse DeletedAt field %s: %w", fieldName, err)
						}
						fieldValue.Set(reflect.ValueOf(gorm.DeletedAt{Time: timeValue, Valid: true}))
					}
				}
			default:
				return fmt.Errorf("unsupported field type: %s for field %s", fieldValue.Kind(), fieldName)
			}
		}
	}

	return nil
}

// RedisIncr Add this function to handle atomic increments
func RedisIncr(key string, delta int64) error {
	if DebugEnabled {
		SysLog(fmt.Sprintf("Redis INCR: key=%s, delta=%d", key, delta))
	}
	// 检查键的剩余生存时间
	ttlCmd := RDB.TTL(context.Background(), key)
	ttl, err := ttlCmd.Result()
	if err != nil && !errors.Is(err, redis.Nil) {
		return fmt.Errorf("failed to get TTL: %w", err)
	}

	// 只有在 key 存在且有 TTL 时才需要特殊处理
	if ttl > 0 {
		ctx := context.Background()
		// 开始一个Redis事务
		txn := RDB.TxPipeline()

		// 减少余额
		decrCmd := txn.IncrBy(ctx, key, delta)
		if err := decrCmd.Err(); err != nil {
			return err // 如果减少失败，则直接返回错误
		}

		// 重新设置过期时间，使用原来的过期时间
		txn.Expire(ctx, key, ttl)

		// 执行事务
		_, err = txn.Exec(ctx)
		return err
	}
	return nil
}

func RedisHIncrBy(key, field string, delta int64) error {
	if DebugEnabled {
		SysLog(fmt.Sprintf("Redis HINCRBY: key=%s, field=%s, delta=%d", key, field, delta))
	}
	ttlCmd := RDB.TTL(context.Background(), key)
	ttl, err := ttlCmd.Result()
	if err != nil && !errors.Is(err, redis.Nil) {
		return fmt.Errorf("failed to get TTL: %w", err)
	}

	if ttl > 0 {
		ctx := context.Background()
		txn := RDB.TxPipeline()

		incrCmd := txn.HIncrBy(ctx, key, field, delta)
		if err := incrCmd.Err(); err != nil {
			return err
		}

		txn.Expire(ctx, key, ttl)

		_, err = txn.Exec(ctx)
		return err
	}
	return nil
}

func RedisHSetField(key, field string, value interface{}) error {
	if DebugEnabled {
		SysLog(fmt.Sprintf("Redis HSET field: key=%s, field=%s, value=%v", key, field, value))
	}
	ttlCmd := RDB.TTL(context.Background(), key)
	ttl, err := ttlCmd.Result()
	if err != nil && !errors.Is(err, redis.Nil) {
		return fmt.Errorf("failed to get TTL: %w", err)
	}

	if ttl > 0 {
		ctx := context.Background()
		txn := RDB.TxPipeline()

		hsetCmd := txn.HSet(ctx, key, field, value)
		if err := hsetCmd.Err(); err != nil {
			return err
		}

		txn.Expire(ctx, key, ttl)

		_, err = txn.Exec(ctx)
		return err
	}
	return nil
}

type redisDualWriteHook struct {
	secondary *redis.Client
	strict    bool
}

func newRedisDualWriteHook(secondary *redis.Client, strict bool) *redisDualWriteHook {
	return &redisDualWriteHook{secondary: secondary, strict: strict}
}

func (h *redisDualWriteHook) BeforeProcess(ctx context.Context, cmd redis.Cmder) (context.Context, error) {
	return ctx, nil
}

func (h *redisDualWriteHook) AfterProcess(ctx context.Context, cmd redis.Cmder) error {
	// 主库命令本身失败，不镜像到副库
	if cmd.Err() != nil && cmd.Err() != redis.Nil {
		return nil
	}
	if !shouldMirrorRedisCommand(cmd) {
		return nil
	}
	args := cloneRedisArgs(cmd.Args())
	if len(args) == 0 {
		return nil
	}

	if h.strict {
		// Strict 模式：同步写副库。
		// 注意：此时主库已写入成功，若副库失败，go-redis 会将错误设置到原始 cmd 上，
		// 调用方会收到错误，但主库数据已写入，需业务层决定是否补偿。
		_, err := h.secondary.Do(ctx, args...).Result()
		if err != nil {
			SysError("redis dual-write failed (strict): " + err.Error())
		}
		return err
	}

	go func(a []interface{}) {
		_, err := h.secondary.Do(context.Background(), a...).Result()
		if err != nil {
			SysError("redis dual-write failed: " + err.Error())
		}
	}(args)
	return nil
}

func (h *redisDualWriteHook) BeforeProcessPipeline(ctx context.Context, cmds []redis.Cmder) (context.Context, error) {
	return ctx, nil
}

func (h *redisDualWriteHook) AfterProcessPipeline(ctx context.Context, cmds []redis.Cmder) error {
	toMirror := make([][]interface{}, 0, len(cmds))
	for _, cmd := range cmds {
		// 跳过主库已失败的命令，避免将无效操作同步到副库
		if cmd.Err() != nil && cmd.Err() != redis.Nil {
			continue
		}
		if shouldMirrorRedisCommand(cmd) {
			args := cloneRedisArgs(cmd.Args())
			if len(args) > 0 {
				toMirror = append(toMirror, args)
			}
		}
	}
	if len(toMirror) == 0 {
		return nil
	}

	execMirror := func(c context.Context, all [][]interface{}) error {
		pipe := h.secondary.Pipeline()
		for _, args := range all {
			pipe.Do(c, args...)
		}
		_, err := pipe.Exec(c)
		if err != nil {
			SysError("redis dual-write pipeline failed: " + err.Error())
		}
		return err
	}

	if h.strict {
		return execMirror(ctx, toMirror)
	}

	go func(all [][]interface{}) {
		_ = execMirror(context.Background(), all)
	}(toMirror)
	return nil
}

func cloneRedisArgs(args []interface{}) []interface{} {
	out := make([]interface{}, len(args))
	copy(out, args)
	return out
}

func shouldMirrorRedisCommand(cmd redis.Cmder) bool {
	name := strings.ToLower(cmd.Name())

	if name == "script" {
		args := cmd.Args()
		if len(args) >= 2 {
			if sub, ok := args[1].(string); ok {
				sub = strings.ToLower(sub)
				return sub == "load" || sub == "flush"
			}
		}
		return false
	}

	switch name {
	case "set", "setex", "mset", "msetnx",
		"del", "unlink", "expire", "pexpire",
		"incr", "incrby", "decr", "decrby",
		"hset", "hsetnx", "hmset", "hdel", "hincrby",
		"lpush", "rpush", "ltrim",
		"eval", "evalsha":
		return true
	default:
		return false
	}
}
