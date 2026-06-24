/**
 * @skill migration-example
 * @description Golden example of TypeORM migration file — up() and down() methods, snake_case columns, indexes, foreign keys. Use as pattern when writing database migrations.
 */
/**
 * EXAMPLE MIGRATION — ticket 71000
 * File naming: {timestamp}-{PascalCaseDescription}.ts
 * Class naming: {PascalCaseDescription}{timestamp}
 * Always: transaction wrap, up() + down(), IF NOT EXISTS/IF EXISTS
 * Requirements: AC-71000-011, AC-71000-018, BR-71000-001
 */
import { MigrationInterface, QueryRunner } from 'typeorm';

export class AddBrandNameUniqueIndex1776000000000 implements MigrationInterface {
  public async up(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.startTransaction();
    try {
      // BR-71000-001: unique case-insensitive among active brands
      await queryRunner.query(`
        CREATE UNIQUE INDEX IF NOT EXISTS idx_brands_name_lower_active
        ON brands(LOWER(name_vi))
        WHERE deleted_at IS NULL
      `);

      // AC-71000-003: search performance
      await queryRunner.query(`
        CREATE INDEX IF NOT EXISTS idx_brands_name_search
        ON brands(name_vi varchar_pattern_ops)
        WHERE deleted_at IS NULL
      `);

      await queryRunner.commitTransaction();
    } catch (err) {
      await queryRunner.rollbackTransaction();
      throw err;
    }
  }

  public async down(queryRunner: QueryRunner): Promise<void> {
    await queryRunner.startTransaction();
    try {
      await queryRunner.query(`DROP INDEX IF EXISTS idx_brands_name_lower_active`);
      await queryRunner.query(`DROP INDEX IF EXISTS idx_brands_name_search`);
      await queryRunner.commitTransaction();
    } catch (err) {
      await queryRunner.rollbackTransaction();
      throw err;
    }
  }
}
