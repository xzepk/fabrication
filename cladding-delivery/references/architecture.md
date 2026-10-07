# Architecture

## 目标架构

```text
Agent / User
    |
    v
Master Skill / deterministic CLI
    |
    +--> CAD Parser Layer ---------> Canonical CAD / Engineering Schema
    |       +-- ACadSharp (DWG)
    |       +-- ezdxf (explicit DXF)
    |
    +--> Engineering Rules --------> scope / material / node / panelization
    |
    +--> Geometry Provider --------> geometry artifacts
    |       +-- OCCT/CadQuery [default]
    |       +-- Rhino adapter [optional]
    |
    +--> Fabrication Provider -----> unfold/bend-specific outputs
    |
    +--> Nesting + BOM ------------> review manufacturing data
    |
    `--> Verification / Package ---> REVIEW delivery package
```

## 分层原则

1. **CAD Parser** 只回答“图纸里有什么”，不决定工程做法。
2. **Engineering Model/Rules** 决定构件语义、材料、分板、节点和复尺采用值。
3. **Geometry Provider** 只做确定性几何构造/求交/测量/导出。
4. **Fabrication Provider** 负责折弯、展开、工艺补偿等制造规则。
5. **Agent** 负责编排、解释和发起人工确认，不成为数值真值源。

## Provider 路由

默认 `occt`。不要自动切到 Rhino；Provider 改变必须来自项目配置或明确授权，并写入 run manifest。
