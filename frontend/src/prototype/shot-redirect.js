// 保留所有连接与镜头定位参数，旧书签进入 main 工作台。
const target = new URL("./workspace.html", location.href);
target.search = location.search;
location.replace(target);
