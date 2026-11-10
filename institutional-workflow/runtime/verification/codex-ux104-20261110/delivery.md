# UX104 原库分类修复

删除前端PARENT三大类映射。正式库直接使用逐因子原category及factorCatalog.libraryLabel，复用builtinCategoryLabelsFromFactors/SV_CATEGORY_LABEL_ORDER，SV编号不显示成分类名。真实12类按现有chips展示计数，搜索独立一行且可与分类/真实资产标签组合。331同源目录仍按library+factor_name去重，导入状态、参考指标与准入行为不改。全库公用12标签集合不当作每个因子标签；批准研究资产的真实tags保留。

后端imports INSERT补上第11个绑定category；现有目录不重导入、不回测、不在线写入。此源码尚未重载到18799，未来只在批准目标库切换窗口加载。

验证：
- categories-components.log：2个实际组件，331去重/12分类计数/组合检索/SV编号回退/平台标签隔离/研究标签保留通过；7.822秒，峰439046144字节。
- imports-isolated.log：6个后端专项通过，新增严格校验SQL占位符数及首次插入原category；既有双卫兵入口禁止真实PG和网络。
- final-build.log：本批UX103+104最终唯一构建exit0，34.925秒/峰2366111744字节，无停止。完整命令见各resources.json。

命令：backend现有解释器运行scripts/run_quant_isolated_tests.py tests/test_quant_factor_imports.py；前端run-node-bounded.py categories-components 45 --import tsx --test --test-concurrency=1 --test-timeout=15000 tests/quantFactorLibraryCategories.test.tsx；同runner final-build 90 npm-cli.js run build。

分类真实UI组合筛选由PM另记，开发不把合成元数据组件用例称为在线数据验收。没有新模型、行情、迁移、重导入或服务重载。独立库c0df311仍prepared_verified_not_loaded。
