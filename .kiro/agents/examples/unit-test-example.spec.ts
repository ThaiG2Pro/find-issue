/**
 * @skill unit-test-example
 * @description Golden example of NestJS unit test — mock dependencies, AC-ID in test names, happy path + error path, describe/it structure. Use as pattern when writing service/controller tests.
 */
/**
 * EXAMPLE UNIT TEST — ticket 71000
 * Rules:
 * - EVERY it() includes AC-ID: it('should ... (AC-71000-001)')
 * - Group by user story: describe('US-1: List Brands')
 * - Sub-group: describe('Happy Path') / describe('Error Path')
 * - Mock ALL external dependencies
 */
import { Test, TestingModule } from '@nestjs/testing';
import { getRepositoryToken } from '@nestjs/typeorm';
import { ConflictException, NotFoundException, BadRequestException } from '@nestjs/common';
import { BrandService } from './brand.service';
import { Brand } from './entities/brand.entity';

describe('BrandService', () => {
  let service: BrandService;
  let brandRepo: any;

  const mockQb = {
    where: jest.fn().mockReturnThis(),
    andWhere: jest.fn().mockReturnThis(),
    orderBy: jest.fn().mockReturnThis(),
    skip: jest.fn().mockReturnThis(),
    take: jest.fn().mockReturnThis(),
    getManyAndCount: jest.fn(),
    getOne: jest.fn(),
  };

  beforeEach(async () => {
    Object.values(mockQb).forEach((fn) => (fn as jest.Mock).mockReset());
    mockQb.where.mockReturnThis();
    mockQb.andWhere.mockReturnThis();
    mockQb.orderBy.mockReturnThis();
    mockQb.skip.mockReturnThis();
    mockQb.take.mockReturnThis();

    brandRepo = {
      createQueryBuilder: jest.fn().mockReturnValue(mockQb),
      findOne: jest.fn(),
      save: jest.fn(),
      softDelete: jest.fn(),
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        BrandService,
        { provide: getRepositoryToken(Brand), useValue: brandRepo },
      ],
    }).compile();

    service = module.get<BrandService>(BrandService);
  });

  afterEach(() => jest.clearAllMocks());

  describe('US-1: List Brands', () => {
    describe('Happy Path', () => {
      it('should return paginated brand list (AC-71000-001)', async () => {
        mockQb.getManyAndCount.mockResolvedValue([[{ name: 'Apple' }], 1]);
        const result = await service.listBrands({ page: 1, limit: 20 });
        expect(result.data).toHaveLength(1);
        expect(result.meta.pagination.total).toBe(1);
      });

      it('should search by name case-insensitive (AC-71000-003)', async () => {
        mockQb.getManyAndCount.mockResolvedValue([[{ name: 'Apple' }], 1]);
        await service.listBrands({ page: 1, limit: 20, search: 'apple' });
        expect(mockQb.andWhere).toHaveBeenCalledWith(
          'LOWER(brand.name) LIKE LOWER(:search)',
          { search: '%apple%' },
        );
      });
    });

    describe('Error Path', () => {
      it('should return empty when no match (AC-71000-006)', async () => {
        mockQb.getManyAndCount.mockResolvedValue([[], 0]);
        const result = await service.listBrands({ page: 1, limit: 20, search: 'xyz' });
        expect(result.data).toHaveLength(0);
      });

      it('should throw 400 on invalid pagination (AC-71000-007)', async () => {
        await expect(service.listBrands({ page: 0, limit: 20 })).rejects.toThrow(BadRequestException);
      });
    });
  });

  describe('US-2: Create Brand', () => {
    describe('Happy Path', () => {
      it('should create brand successfully (AC-71000-009, AC-71000-010)', async () => {
        mockQb.getOne.mockResolvedValue(null);
        brandRepo.save.mockResolvedValue({ id: 'uuid', name: 'Samsung', createdAt: new Date() });
        const result = await service.createBrand({ name: 'Samsung' });
        expect(result.id).toBeDefined();
      });
    });

    describe('Error Path', () => {
      it('should throw 409 on duplicate name (AC-71000-011)', async () => {
        mockQb.getOne.mockResolvedValue({ id: 'existing', name: 'apple' });
        await expect(service.createBrand({ name: 'Apple' })).rejects.toThrow(ConflictException);
      });
    });
  });

  describe('US-4: Delete Brand', () => {
    describe('Happy Path', () => {
      it('should soft-delete brand (AC-71000-021)', async () => {
        brandRepo.findOne.mockResolvedValue({ id: 'uuid' });
        brandRepo.softDelete.mockResolvedValue({ affected: 1 });
        await service.deleteBrand('uuid');
        expect(brandRepo.softDelete).toHaveBeenCalledWith('uuid');
      });
    });

    describe('Error Path', () => {
      it('should throw 404 on double-delete (AC-71000-025)', async () => {
        brandRepo.findOne.mockResolvedValue(null);
        await expect(service.deleteBrand('uuid')).rejects.toThrow(NotFoundException);
      });
    });
  });
});
