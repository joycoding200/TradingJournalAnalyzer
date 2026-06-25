import { Link } from "react-router-dom";
import { Button } from "../components/ui";

export default function NotFound() {
  return (
    <div className="flex min-h-[70vh] flex-col items-center justify-center px-4 text-center">
      <div className="mb-4 text-6xl">🔍</div>
      <h1 className="mb-2 text-2xl font-semibold">404</h1>
      <p className="mb-6 text-text-secondary">
        页面不存在
      </p>
      <Link to="/">
        <Button variant="primary">返回首页</Button>
      </Link>
    </div>
  );
}
