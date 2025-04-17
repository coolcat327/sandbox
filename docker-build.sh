#!/bin/bash

# 获取当前时间戳（精确到秒）
get_current_time() {
    echo $(date "+%Y%m%d%H%M%S")
}

# 构建 Docker 镜像
build_docker_image() {
    local platform=$1
    local workdir=$2
    local tag=$3

    cd "$workdir" || { echo "目录切换失败: $workdir"; return 1; }

    echo "开始构建 Docker 镜像..."
    if docker build --platform "$platform" --build-arg DOCKER_BUILDKIT=1 -t "$tag" .; then
        echo "Docker 镜像构建成功"
        return 0
    else
        echo "Docker 镜像构建失败"
        return 1
    fi
}

# 保存 Docker 镜像
save_docker_image() {
    local tag=$1
    local output_dir=$2
    local pre_file_name=$3
    local current_time=$(get_current_time)

    # 确保保存目录存在
    mkdir -p "$output_dir"

    # 保存 Docker 镜像为带有时间戳的 tar 文件
    local tar_file="${output_dir}/${pre_file_name}-${current_time}.tar"
    echo "正在保存 Docker 镜像..."
    docker save "$tag" -o "$tar_file"

    # 判断镜像保存是否成功
    if [ -f "$tar_file" ]; then
        # 使用 gzip 进行压缩
        echo "正在压缩镜像文件..."
        gzip "$tar_file"
        echo "Docker 镜像已成功保存并压缩至 ${tar_file}.gz"
    else
        echo "错误：Docker 镜像保存失败"
    fi
}

# 设置默认值
DEFAULT_WORKDIR="./"
DEFAULT_OUTPUT_DIR="/Users/qt/Desktop/docker_images"
DEFAULT_PLATFORM="linux/amd64"
DEFAULT_VERSION="latest"

# 获取用户输入
echo -n "请输入项目目录（默认：$DEFAULT_WORKDIR ): "
read -r workdir
workdir=${workdir:-$DEFAULT_WORKDIR}

echo -n "请输入镜像保存目录（默认：$DEFAULT_OUTPUT_DIR ): "
read -r output_directory
output_directory=${output_directory:-$DEFAULT_OUTPUT_DIR}

echo -n "请输入目标平台（默认：$DEFAULT_PLATFORM ): "
read -r platform
platform=${platform:-$DEFAULT_PLATFORM}

echo -n "请输入版本号（默认：$DEFAULT_VERSION ): "
read -r version
version=${version:-$DEFAULT_VERSION}

# 设置镜像标签和文件名前缀
image_tag="sandbox:$version"
pre_file_name="sandbox-$version"

# 执行构建和保存
if build_docker_image "$platform" "$workdir" "$image_tag"; then
    save_docker_image "$image_tag" "$output_directory" "$pre_file_name"
else
    echo "构建失败，退出脚本"
    exit 1
fi 