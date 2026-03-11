package model

import (
	"errors"
	"os"
	"strings"

	"github.com/QuantumNous/new-api/common"
	"github.com/glebarez/sqlite"
	"gorm.io/driver/mysql"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

var SecondaryDB *gorm.DB
var DualWriteEnabled bool
var DualWriteStrict bool

func openDualWriteDB(dsn string) (*gorm.DB, error) {
	if strings.HasPrefix(dsn, "postgres://") || strings.HasPrefix(dsn, "postgresql://") {
		return gorm.Open(postgres.New(postgres.Config{
			DSN:                  dsn,
			PreferSimpleProtocol: true,
		}), &gorm.Config{PrepareStmt: true})
	}
	if strings.HasPrefix(dsn, "local") {
		return gorm.Open(sqlite.Open(common.SQLitePath), &gorm.Config{PrepareStmt: true})
	}
	if !strings.Contains(dsn, "parseTime") {
		if strings.Contains(dsn, "?") {
			dsn += "&parseTime=true"
		} else {
			dsn += "?parseTime=true"
		}
	}
	return gorm.Open(mysql.Open(dsn), &gorm.Config{PrepareStmt: true})
}

func InitDualWriteDB() error {
	dsn := os.Getenv("DUAL_WRITE_SQL_DSN")
	if dsn == "" {
		return nil
	}
	db, err := openDualWriteDB(dsn)
	if err != nil {
		return err
	}
	if common.DebugEnabled {
		db = db.Debug()
	}
	SecondaryDB = db
	DualWriteEnabled = true
	DualWriteStrict = common.GetEnvOrDefaultBool("DUAL_WRITE_STRICT", false)

	sqlDB, err := SecondaryDB.DB()
	if err != nil {
		return err
	}
	sqlDB.SetMaxIdleConns(common.GetEnvOrDefault("SQL_MAX_IDLE_CONNS", 100))
	sqlDB.SetMaxOpenConns(common.GetEnvOrDefault("SQL_MAX_OPEN_CONNS", 1000))

	if common.IsMasterNode {
		err = SecondaryDB.AutoMigrate(
			&Channel{}, &Token{}, &User{}, &PasskeyCredential{}, &Option{}, &Redemption{}, &Ability{}, &Log{},
			&Midjourney{}, &TopUp{}, &QuotaData{}, &Task{}, &Model{}, &Vendor{}, &PrefillGroup{}, &Setup{},
			&TwoFA{}, &TwoFABackupCode{}, &Invoice{}, &ReconDiscount{}, &ReconUpstream{}, &ReconResult{},
		)
		if err != nil {
			return err
		}
	}
	registerDualWriteCallbacks()
	common.SysLog("dual-write enabled: primary DB writes will be mirrored to DUAL_WRITE_SQL_DSN")
	return nil
}

func registerDualWriteCallbacks() {
	if DB == nil || SecondaryDB == nil {
		return
	}
	_ = DB.Callback().Create().After("gorm:create").Register("dualwrite:create", dualWriteCallback)
	_ = DB.Callback().Update().After("gorm:update").Register("dualwrite:update", dualWriteCallback)
	_ = DB.Callback().Delete().After("gorm:delete").Register("dualwrite:delete", dualWriteCallback)
}

func ExecWithDualWrite(db *gorm.DB, sqlText string, values ...any) error {
	if db == nil {
		db = DB
	}
	if db == nil {
		return errors.New("primary db is nil")
	}
	res := db.Exec(sqlText, values...)
	if res.Error != nil {
		return res.Error
	}
	if !DualWriteEnabled || SecondaryDB == nil {
		return nil
	}
	secondaryRes := SecondaryDB.Exec(sqlText, values...)
	if secondaryRes.Error != nil {
		common.SysError("dual-write exec failed: " + secondaryRes.Error.Error())
		if DualWriteStrict {
			return secondaryRes.Error
		}
	}
	return nil
}

func dualWriteCallback(tx *gorm.DB) {
	if !DualWriteEnabled || SecondaryDB == nil {
		return
	}
	if tx == nil || tx.Error != nil || tx.Statement == nil {
		return
	}
	sqlText := tx.Statement.SQL.String()
	if sqlText == "" {
		return
	}
	res := SecondaryDB.Exec(sqlText, tx.Statement.Vars...)
	if res.Error != nil {
		common.SysError("dual-write failed: " + res.Error.Error())
		if DualWriteStrict {
			tx.Error = errors.Join(tx.Error, res.Error)
		}
	}
}
