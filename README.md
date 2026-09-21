# BagRoute

投递装袋：按路线订户顺序装袋，重量与体积双约束，超限拒收。

## 启动

```bash
docker compose up --build
```

| 服务 | 地址 |
| --- | --- |
| 前端 | http://localhost:4300 |
| API | http://localhost:9300 |
| API 文档 | http://localhost:9300/docs |
| Postgres | localhost:5444 |

健康检查：`GET http://localhost:9300/api/health`

## 页面

- `/routes` — 路线
- `/stops` — 订户点
- `/pack` — 装袋
- `/bags` — 袋明细
- `/rejects` — 拒收
- `/weights` — 袋重

## 使用说明

1. 查看路线与订户点顺序。
2. 在装袋页选择路线执行双约束装袋。
3. 袋明细与袋重查看结果，拒收页查看超限订户。

## 站点序号约束

- 同一路线内序号必须从 1 起连续且不重复；新增站点只能追加到队尾（`n+1`），跳号或冲突会返回 400 并在站点页显示原因。
- 修改序号在 1..n 范围内移动，途经站点自动顺延；越界修改会失败，已有站点保持不变。
- 站点页提供「重排序号 1..n」操作，把当前路线站点按现有顺序重写为连续序号。
- 装袋严格按序号从小到大，与名称无关。

## 开发与测试

```bash
docker compose exec api pytest -q
```
