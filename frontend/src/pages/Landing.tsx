import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { Button, Card } from "../components/ui";

export default function Landing() {
  const { isLoggedIn } = useAuth();

  return (
    <div className="flex min-h-[80vh] flex-col items-center justify-center px-4 text-center">
      <h1 className="mb-4 text-4xl font-bold">
        TradingJournalAnalyzer
      </h1>
      <p className="mb-8 max-w-[480px] text-lg text-text-secondary">
        上传您的交易交割单，AI 将分析您的交易行为，找出亏损原因并生成改善建议。
      </p>
      <div className="flex gap-4">
        {isLoggedIn ? (
          <Link to="/upload">
            <Button>开始分析</Button>
          </Link>
        ) : (
          <>
            <Link to="/login">
              <Button>登录</Button>
            </Link>
            <Link to="/register">
              <Button variant="outline">注册</Button>
            </Link>
          </>
        )}
      </div>
      <div className="mt-16 grid max-w-[720px] grid-cols-1 gap-6 md:grid-cols-3">
        {[
          { title: "上传交割单", desc: "支持 CSV / Excel 格式，自动识别券商", icon: "📄" },
          { title: "行为分析", desc: "识别追涨、抄底、波段等交易模式", icon: "🔍" },
          { title: "AI 诊断", desc: "生成个性化交易行为诊断报告", icon: "🤖" },
        ].map((item) => (
          <Card key={item.title} className="p-6 text-left">
            <div className="mb-3 text-2xl">{item.icon}</div>
            <h3 className="mb-2 font-medium">{item.title}</h3>
            <p className="text-sm text-text-secondary">
              {item.desc}
            </p>
          </Card>
        ))}
      </div>

      {/* Trust section */}
      <div className="mt-20 w-full max-w-[600px] rounded-2xl border border-border bg-bg-secondary p-6 text-left md:p-8">
        <div className="mb-4 flex items-center gap-2">
          <span className="text-xl">🔒</span>
          <h2 className="text-base font-semibold text-text-primary">你的数据，你做主</h2>
        </div>
        <ul className="space-y-3">
          {[
            "交割单仅用于分析，不上传第三方",
            "可一键彻底删除所有数据",
            "默认不进入案例库",
            "仅在您授权后匿名贡献案例",
          ].map((item) => (
            <li key={item} className="flex items-start gap-2 text-sm text-text-secondary">
              <span className="mt-px shrink-0 text-success">✓</span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
